import base64
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from native_meetings import decode_meeting, select_current, MeetingEngine, stable_snapshot
from desktop_service import DesktopService, UserError, clean_abandoned_snapshots
from desktop_service import discover_databases
from tests.test_desktop_service import sample_database


UID = '9007199254740993'
CODE = '9007199254740999'


def payload():
    item = dict(content='原文  保留\n<script>示例</script>', name='示例成员',
                vid='7', speak_time='1500', content_id='1')
    return [0, {
        'base_info': {'record_item': {'subject': base64.b64encode('演示会议'.encode()).decode(),
                                      'begin_time': '1788501600'}},
        'text_convert_list': {'share_items': [
            {'record_start_time': '1788501600', 'items': [item, dict(item, content_id='2')]},
            {'record_start_time': '1788505200', 'items': [dict(item, content_id='3')]}]},
    }, 1790000000, None, {'meeting_code': CODE}, None, 1790000000000]


def record(seq=1, value=None, uid=UID, kind=1):
    key = f'_https://app.work.weixin.qq.com\0\x01ww0_{uid}_/xweb/smartMinutes/getMeetingNotes/{CODE}'.encode()
    if value is None:
        value = b'\0' + json.dumps(payload(), ensure_ascii=False).encode('utf-16le')
    return SimpleNamespace(key=key, value=value, sequence_number=seq, record_type=kind)


class MeetingTests(unittest.TestCase):
    def test_latest_tombstone_and_other_account_are_not_exported(self):
        rows = [record(), record(2, b'', kind=0), record(3, uid='123')]
        self.assertEqual(select_current(rows, UID), {})

    def test_latest_record_and_exact_large_id(self):
        rows = select_current([record(5), record(2)], UID)
        self.assertEqual(list(rows), [CODE])
        self.assertEqual(rows[CODE].sequence_number, 5)

    def test_preserves_repeated_text_speakers_and_segment_offsets(self):
        title, result, started = decode_meeting(CODE, record().value)
        self.assertEqual(title, '演示会议')
        self.assertEqual(len(result['records']), 3)
        self.assertEqual([r['session'] for r in result['records']], [1, 1, 2])
        self.assertEqual(result['records'][0]['text'], payload()[1]['text_convert_list']['share_items'][0]['items'][0]['content'])
        self.assertEqual(result['records'][0]['time'], '2026-09-04 14:00:01.500')
        self.assertEqual(result['records'][2]['time'], '2026-09-04 15:00:01.500')
        self.assertFalse(result['server_completeness_verified'])
        self.assertEqual(started, 1788501600)

    def test_mismatch_and_partial_malformed_payload_fail(self):
        with self.assertRaises(ValueError):
            decode_meeting('12', record().value)
        bad = payload()
        bad[1]['text_convert_list']['share_items'][0]['items'][1]['content'] = None
        with self.assertRaises(ValueError):
            decode_meeting(CODE, b'\0' + json.dumps(bad).encode('utf-16le'))

    def test_empty_transcript_not_successful_export(self):
        bad = payload()
        bad[1]['text_convert_list']['share_items'] = []
        with self.assertRaises(ValueError):
            decode_meeting(CODE, b'\0' + json.dumps(bad).encode('utf-16le'))

    def test_meeting_engine_does_not_use_facechat_key(self):
        with patch('native_meetings.read_current', return_value={CODE: record()}), \
             patch('native_export.database_key', side_effect=AssertionError('no key access')):
            rooms = MeetingEngine().catalog(Path('voice_room5.db'), Path('state'), lambda _: None)
        self.assertEqual(rooms[0]['room_id'], CODE)

    def test_meeting_only_profile_needs_no_facechat_or_contacts_database(self):
        from tests.test_native_transcript import field
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root/'Profiles/example/io_data.json'
            identity.parent.mkdir(parents=True)
            identity.write_text(json.dumps({'user_info': base64.b64encode(field(1, int(UID))).decode()}))
            (root/UID).mkdir()
            found = discover_databases([root/'Profiles'], source='meeting')
            self.assertEqual([r['path'] for r in found['candidates']], [str(identity.resolve())])
            service = DesktopService(root/'state')
            with patch('native_meetings.read_current', return_value={CODE: record()}):
                result = service.connect(str(identity), True, lambda _: None, source='meeting')
            self.assertEqual(len(result['rooms']), 1)

    def test_service_meeting_mode_export_and_revoke(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = sample_database(root/'Profiles/example/voice_room5.db')
            service = DesktopService(root/'state')
            with patch('native_meetings.read_current', return_value={CODE: record()}), \
                 patch('native_export.database_key', side_effect=AssertionError('must not decrypt')):
                result = service.connect(str(db), True, lambda _: None, source='meeting')
                self.assertEqual(result['source'], 'meeting')
                exported = service.export(CODE, str(root/'exports'), lambda _: None)
            self.assertEqual(exported['passages'], 3)
            self.assertTrue(any('服务器' in w for w in exported['warnings']))
            self.assertIn('服务器', service.output_file(exported['id'], 'md').read_text(encoding='utf-8'))
            service.revoke()
            with self.assertRaises(UserError):
                service.export(CODE, str(root/'exports'), lambda _: None)

    def test_invalid_source_clears_existing_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            service = DesktopService(directory)
            service.database = Path('old')
            service.rooms = [{'room_id': CODE}]
            with self.assertRaises(UserError):
                service.connect('anything', True, lambda _: None, source='unknown')
            self.assertIsNone(service.database)
            self.assertEqual(service.rooms, [])

    def test_dead_snapshot_cleanup_handles_leveldb_but_keeps_unknown_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root/'profiles/example/snapshot-123-test'
            snapshot.mkdir(parents=True)
            for name in ['CURRENT', 'MANIFEST-000001', '000003.ldb', '000004.log', 'keep.txt']:
                (snapshot/name).write_bytes(b'synthetic')
            with patch('desktop_service.process_running', return_value=False):
                clean_abandoned_snapshots(root)
            self.assertEqual([p.name for p in snapshot.iterdir()], ['keep.txt'])

    def test_snapshot_includes_previous_log_and_excludes_obsolete_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache'
            cache.mkdir()
            (cache/'CURRENT').write_text('MANIFEST-000001\n')
            for name in ['MANIFEST-000001', '000002.log', '000003.log', '000004.ldb', '000005.ldb']:
                (cache/name).write_bytes(b'synthetic')
            version = SimpleNamespace(current_log='000003.log', active_files={0: {'000004.ldb': None}})
            with patch('dfindexeddb.leveldb.descriptor.FileReader') as reader, \
                 patch('native_leveldb.validate_log'):
                reader.return_value.GetLatestVersion.return_value = version
                reader.return_value.GetVersionEdits.return_value = iter([SimpleNamespace(prev_log_number=2)])
                with stable_snapshot(cache, root/'state') as (snapshot, names):
                    self.assertEqual(names, {'000002.log', '000003.log', '000004.ldb'})
                    self.assertFalse((snapshot/'000005.ldb').exists())
                self.assertFalse(snapshot.exists())

    def test_snapshot_refuses_changed_data_and_cleans_temporary_files(self):
        import native_meetings
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache'
            cache.mkdir()
            (cache/'CURRENT').write_text('MANIFEST-000001\n')
            (cache/'MANIFEST-000001').write_bytes(b'synthetic')
            original = native_meetings._read
            count = 0
            def changing(folder, name):
                nonlocal count
                data = original(folder, name)
                if name == 'CURRENT':
                    count += 1
                    if count == 2:
                        return data + b'changed'
                return data
            with patch('dfindexeddb.leveldb.descriptor.FileReader') as reader, \
                 patch('native_leveldb.validate_log'), \
                 patch('native_meetings._read', side_effect=changing):
                reader.return_value.GetLatestVersion.return_value = SimpleNamespace(current_log=None, active_files={})
                reader.return_value.GetVersionEdits.return_value = iter([])
                with self.assertRaises(ValueError):
                    with stable_snapshot(cache, root/'state'):
                        self.fail('Changed snapshot must not be yielded')
            self.assertEqual(list((root/'state').iterdir()), [])
