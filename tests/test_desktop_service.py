import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_service import DesktopService, UserError, discover_databases, validate_database_path


def sample_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\0' * 16 + bytes.fromhex('1000020200402020') + b'\0' * (4096 - 24))
    return path


class FakeEngine:
    def catalog(self, database, state, progress):
        return [{'room_id': '9007199254740993', 'title': 'A repeated title', 'started': 10},
                {'room_id': '9007199254740993' + '1', 'title': 'A repeated title', 'started': 20}]


class DesktopServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = sample_database(self.root / 'profiles/account/voice_room5.db')
        self.service = DesktopService(self.root / 'state', engine=FakeEngine(), roots=[self.root / 'profiles'])

    def test_discovery_keeps_multiple_accounts_and_deduplicates(self):
        sample_database(self.root / 'profiles/other/voice_room5.db')
        result = discover_databases([self.root / 'profiles', self.root / 'profiles/account'])
        self.assertEqual(len(result['candidates']), 2)

    def test_discovery_does_not_walk_media_below_a_found_profile(self):
        for index in range(15):
            (self.db.parent / 'media' / str(index)).mkdir(parents=True)
        result = discover_databases([self.root / 'profiles'])
        self.assertEqual(len(result['candidates']), 1)
        self.assertLessEqual(result['scanned_folders'], 2)

    def test_invalid_database_is_actionable(self):
        bad = self.root / 'voice_room5.db'
        bad.write_bytes(b'wrong format')
        with self.assertRaises(UserError) as error:
            validate_database_path(bad)
        self.assertEqual(error.exception.code, 'unsupported_database')

    def test_connect_requires_explicit_local_consent(self):
        with self.assertRaises(UserError) as error:
            self.service.connect(str(self.db), False, lambda _: None)
        self.assertEqual(error.exception.code, 'consent_required')
        self.assertEqual(self.service.rooms, [])

    def test_consent_is_saved_and_room_ids_are_exact_strings(self):
        result = self.service.connect(str(self.db), True, lambda _: None)
        self.assertEqual(result['rooms'][0]['room_id'], '9007199254740993')
        again = DesktopService(self.root / 'state', engine=FakeEngine(), roots=[])
        self.assertTrue(again.has_consent(str(self.db)))
        self.assertEqual(len(result['rooms']), 2)

    def test_changing_account_failure_clears_previous_room_selection(self):
        self.service.connect(str(self.db), True, lambda _: None)
        with self.assertRaises(UserError):
            self.service.connect(str(self.root / 'missing.db'), True, lambda _: None)
        self.assertEqual(self.service.rooms, [])

    def test_revoke_removes_access_and_room_state(self):
        self.service.connect(str(self.db), True, lambda _: None)
        self.service.revoke()
        self.assertFalse(self.service.has_consent(str(self.db)))
        self.assertEqual(self.service.rooms, [])

    def test_stale_or_unknown_room_is_rejected(self):
        self.service.connect(str(self.db), True, lambda _: None)
        with self.assertRaises(UserError) as error:
            self.service.export('unknown', str(self.root / 'output'), lambda _: None)
        self.assertEqual(error.exception.code, 'choose_recording')

    def test_abandoned_snapshot_is_removed_but_active_snapshot_is_kept(self):
        abandoned = self.root / 'state/profiles/sample/snapshot-500-old'
        active = self.root / 'state/profiles/sample/snapshot-501-active'
        for directory in (abandoned, active):
            directory.mkdir(parents=True)
            (directory / 'voice-room.db').write_bytes(b'synthetic plaintext')
        with patch('desktop_service.process_running', side_effect=lambda pid: pid == 501):
            DesktopService(self.root / 'state', engine=FakeEngine(), roots=[])
        self.assertFalse(abandoned.exists())
        self.assertTrue((active / 'voice-room.db').exists())
