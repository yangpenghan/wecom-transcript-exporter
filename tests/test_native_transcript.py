import sqlite3
import unittest

from native_transcript import decode_fields, decode_text, extract_room, room_catalog


def vint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def field(number, value):
    if isinstance(value, int):
        return vint(number << 3) + vint(value)
    return vint((number << 3) | 2) + vint(len(value)) + value


def message(text='', flag=0, event='', title=''):
    body = field(1, field(1, 0) + field(2, field(1, text.encode())))
    if title:
        body = field(10, ('根据面聊记录，修改面聊名称为“' + title + '”').encode())
    return field(8, body) + field(13, flag) + field(15, event.encode())


class NativeTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('CREATE TABLE voice_room_message (lid INTEGER,rid INTEGER,seq INTEGER,room_id INTEGER,sender INTEGER,sender_name TEXT,message_type INTEGER,content_type INTEGER,send_time INTEGER,blob BLOB)')

    def tearDown(self):
        self.conn.close()

    def add(self, rid, text='', flag=0, event='', title='', kind=2):
        self.conn.execute('INSERT INTO voice_room_message VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (rid, rid, rid, 42, 0, '发言人1', 110, kind, 1792375200 + rid,
                           message(text, flag, event, title)))

    def test_verbatim_text_and_repeated_utterances(self):
        original = 'Hello.  中文\n第二行；😀'
        self.add(1, original)
        self.add(2, original)
        result = extract_room(self.conn, 42)
        self.assertEqual([r['text'] for r in result['records']], [original, original])

    def test_nonzero_state_is_reported_and_excluded(self):
        self.add(1, 'visible')
        self.add(2, 'flagged', flag=1)
        result = extract_room(self.conn, 42)
        self.assertEqual([r['text'] for r in result['records']], ['visible'])
        self.assertEqual(result['excluded_nonzero_state'], 1)

    def test_end_does_not_discard_resumed_segment(self):
        self.add(1, 'first')
        self.add(2, event='voice_room_end_42_1', title='Test title', kind=2386)
        self.add(3, event='restart_voice_room_tips_42_2', kind=1011)
        self.add(4, 'second')
        self.add(5, event='voice_room_end_42_3', kind=2386)
        result = extract_room(self.conn, 42)
        self.assertEqual([r['session'] for r in result['records']], [1, 2])
        self.assertTrue(result['last_segment_ended'])
        self.assertEqual(room_catalog(self.conn)[0]['title'], 'Test title')

    def test_missing_ids_are_reported(self):
        self.add(1, 'a')
        self.add(3, 'b')
        self.assertEqual(extract_room(self.conn, 42)['missing_id_ranges'], [[2, 2]])

    def test_malformed_payload_fails_instead_of_silently_dropping_text(self):
        with self.assertRaises(ValueError):
            decode_fields(b'\x0a\xff')
        with self.assertRaises(ValueError):
            decode_text(field(8, b'not protobuf'))


if __name__ == '__main__':
    unittest.main()
