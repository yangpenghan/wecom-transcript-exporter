import contextlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from desktop_service import NativeEngine, DesktopService
from native_transcript import extract_room
from tests.test_native_transcript import message


class SpeakerEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE voice_room_message(rid INTEGER,room_id INTEGER,sender INTEGER,sender_name TEXT,content_type INTEGER,send_time INTEGER,blob BLOB)')
        for rid, sender, name, text in [(1, 9007199254740993, '', '原文  一\n下一行'), (2, 7, '原始姓名', '重复'), (3, 7, '原始姓名', '重复')]:
            self.conn.execute('INSERT INTO voice_room_message VALUES (?,?,?,?,?,?,?)', (rid, 42, sender, name, 2, 1792375200+rid, message(text)))
        self.engine = NativeEngine()

    def snapshot(self, *args):
        return contextlib.nullcontext(self.conn)

    def test_default_does_not_access_contacts(self):
        with patch.object(self.engine, 'snapshot', self.snapshot), patch('native_contacts.resolve_names') as resolve:
            _, result = self.engine.extract(Path('voice_room5.db'), Path('state'), '42', lambda _: None)
        resolve.assert_not_called()
        self.assertEqual(result['records'][0]['speaker'], '成员1')

    def test_exact_mapping_preserves_native_names_and_every_other_field(self):
        before = extract_room(self.conn, 42)
        mapping = {'9007199254740993': '示例姓名', '7': '不可覆盖'}
        report = {'status': 'complete', 'requested': 1, 'resolved': 1}
        with patch.object(self.engine, 'snapshot', self.snapshot), patch('native_contacts.resolve_names', return_value=(mapping, report)) as resolve:
            _, after = self.engine.extract(Path('voice_room5.db'), Path('state'), '42', lambda _: None, resolve_speakers=True)
        self.assertEqual(set(resolve.call_args.args[2]), {'9007199254740993'})
        self.assertEqual([r['speaker'] for r in after['records']], ['示例姓名', '原始姓名', '原始姓名'])
        for a, b in zip(before['records'], after['records']):
            self.assertEqual({k:v for k,v in a.items() if k!='speaker'}, {k:v for k,v in b.items() if k!='speaker'})

    def test_optional_failure_keeps_transcript_and_reports_it(self):
        report = {'status': 'unavailable', 'requested': 1, 'resolved': 0}
        with patch.object(self.engine, 'snapshot', self.snapshot), patch('native_contacts.resolve_names', return_value=({}, report)):
            _, after = self.engine.extract(Path('voice_room5.db'), Path('state'), '42', lambda _: None, resolve_speakers=True)
        self.assertEqual(after['records'], extract_room(self.conn, 42)['records'])
        self.assertEqual(after['speaker_resolution'], report)

    def test_crash_cleanup_removes_staging_only_for_dead_processes(self):
        from desktop_service import clean_abandoned_snapshots
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dead = root/'profiles'/'sample-contacts'/'snapshot-123-dead'
            active = root/'profiles'/'sample-contacts'/'snapshot-456-active'
            for folder in [dead, active]:
                folder.mkdir(parents=True)
                (folder/'.wecom-synthetic.db').write_bytes(b'synthetic plaintext')
            with patch('desktop_service.process_running', side_effect=lambda pid: pid == 456):
                clean_abandoned_snapshots(root)
            self.assertFalse(dead.exists())
            self.assertTrue((active/'.wecom-synthetic.db').exists())

    def test_revoke_removes_contact_and_recording_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            service = DesktopService(Path(directory))
            for name in ['sample', 'sample-contacts']:
                key = service.state/'profiles'/name/'voice-room-key.dpapi'
                key.parent.mkdir(parents=True)
                key.write_bytes(b'synthetic protected state')
            service.revoke()
            self.assertEqual(list(service.state.glob('profiles/*/*.dpapi')), [])
