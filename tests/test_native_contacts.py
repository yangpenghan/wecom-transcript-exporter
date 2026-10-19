import base64
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_native_transcript import field
from native_contacts import contact_database, query_names, resolve_names


class ContactNamesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'Profiles/example/voice_room5.db'
        self.db.parent.mkdir(parents=True)
        self.db.touch()
        self.uid = 9007199254740993
        self.contacts = self.root / str(self.uid) / 'Data/user.db'
        self.contacts.parent.mkdir(parents=True)
        self.contacts.touch()
        identity = base64.b64encode(field(1, self.uid) + field(2, '示例用户'.encode())).decode()
        (self.db.parent / 'io_data.json').write_text(json.dumps({'user_info': identity}))

    def test_exact_current_account_only(self):
        other = self.root / '1234/Data/user.db'
        other.parent.mkdir(parents=True)
        other.touch()
        self.assertEqual(contact_database(self.db), self.contacts.resolve())
        self.contacts.unlink()
        with self.assertRaises((OSError, ValueError)):
            contact_database(self.db)

    def test_invalid_identity_never_guesses_another_account(self):
        (self.db.parent / 'io_data.json').write_text('{"user_info":"not base64"}')
        with self.assertRaises(ValueError):
            contact_database(self.db)

    def test_duplicate_identity_field_is_rejected(self):
        identity = base64.b64encode(field(1, self.uid) + field(1, 1234)).decode()
        (self.db.parent / 'io_data.json').write_text(json.dumps({'user_info': identity}))
        with self.assertRaises(ValueError):
            contact_database(self.db)

    def test_exact_large_ids_only_and_conflicts_stay_unknown(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute('CREATE TABLE user_table(id INTEGER,name TEXT)')
        conn.executemany('INSERT INTO user_table VALUES (?,?)', [
            (self.uid, '示例甲'), (self.uid, '示例甲'), (7, '示例乙'),
            (7, '另一姓名'), (8, ''), (9, '不应查询的成员')])
        names = query_names(conn, [str(self.uid), '7', '8', '0', 'not-an-id'])
        self.assertEqual(names, {str(self.uid): '示例甲'})

    def test_missing_identity_returns_actionable_fallback(self):
        (self.db.parent / 'io_data.json').unlink()
        names, report = resolve_names(self.db, self.root / 'state', ['7'], lambda _: None)
        self.assertEqual(names, {})
        self.assertEqual(report['status'], 'unavailable')

    def test_no_missing_speakers_does_not_read_contacts(self):
        with patch('native_contacts.contact_database', side_effect=AssertionError('must not read')):
            names, report = resolve_names(self.db, self.root / 'state', [], lambda _: None)
        self.assertEqual(names, {})
        self.assertEqual(report['status'], 'not_needed')

    def test_query_only_resolves_requested_ids(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute('CREATE TABLE user_table(id INTEGER,name TEXT)')
        conn.executemany('INSERT INTO user_table VALUES (?,?)', [(1, '示例甲'), (2, '示例乙')])
        queries = []
        conn.set_trace_callback(queries.append)
        self.assertEqual(query_names(conn, ['1']), {'1': '示例甲'})
        self.assertEqual(len(queries), 1)
        self.assertIn('WHERE id IN', queries[0])
