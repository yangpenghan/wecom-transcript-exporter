# Adapted from freanocank/wecom-agent, MIT; see native_support/LICENSE.wecom-agent.
import contextlib
import os
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_support import wal_snapshot as wal
from native_support import wxwork_crypto as crypto
from native_support.local_io import connect_readonly

PAGE = 4096
KEY = bytes(range(16))


def make_wal(frames, byteorder="<", salts=b"abcdefgh"):
    magic = 0x377f0682 if byteorder == "<" else 0x377f0683
    header = struct.pack(">IIII", magic, 3007000, PAGE, 0) + salts
    state = wal._checksum(header, byteorder)
    result = header + struct.pack(">II", *state)
    for number, size, page in frames:
        prefix = struct.pack(">II", number, size)
        state = wal._checksum(prefix + page, byteorder, state)
        result += prefix + salts + struct.pack(">II", *state) + page
    return result


def encrypted(page, number):
    if number == 1:
        return crypto._encrypt_page1(KEY, page)
    return crypto._aes_cbc_enc(crypto.derive_page_key(KEY, number), crypto.generate_initial_vector(number), page)


class WalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_only_committed_pages_and_current_generation_are_used(self):
        for order in ("<", ">"):
            with self.subTest(byteorder=order):
                main = b"a" * PAGE + b"b" * PAGE
                frames = make_wal([(2, 2, b"c" * PAGE), (1, 0, b"d" * PAGE)], order)
                self.assertEqual(wal.merge_committed_pages(main, frames + b"partial"), b"a" * PAGE + b"c" * PAGE)
                stale = make_wal([(1, 2, b"x" * PAGE)], order, b"old-salt")[32:]
                self.assertEqual(wal.merge_committed_pages(main, frames + stale), b"a" * PAGE + b"c" * PAGE)

    def test_growth_shrink_and_missing_pages(self):
        main = b"a" * PAGE + b"b" * PAGE
        self.assertEqual(wal.merge_committed_pages(main, make_wal([(3, 3, b"c" * PAGE)])), main + b"c" * PAGE)
        self.assertEqual(wal.merge_committed_pages(main, make_wal([(1, 1, b"c" * PAGE)])), b"c" * PAGE)
        with self.assertRaisesRegex(ValueError, "missing"):
            wal.merge_committed_pages(main, make_wal([(1, 1, b"c" * PAGE), (3, 3, b"d" * PAGE)]))

    def test_corrupted_header_frame_and_payload_fail_closed(self):
        for position in (24, 48, 100):
            data = bytearray(make_wal([(1, 1, b"b" * PAGE)]))
            data[position] ^= 1
            with self.subTest(position=position), self.assertRaisesRegex(ValueError, "checksum"):
                wal.merge_committed_pages(b"a" * PAGE, data)

    def test_changing_main_wal_pair_is_retried_and_rejected(self):
        source = self.root / "input.db"
        source.write_bytes(b"x" * PAGE)
        with patch.object(wal, "_metadata", side_effect=iter(range(20))), self.assertRaisesRegex(ValueError, "changed"):
            wal.read_snapshot(source)

    def test_real_sqlite_wal_is_decrypted_into_a_complete_committed_snapshot(self):
        plain = self.root / "live.db"
        conn = sqlite3.connect(plain)
        self.addCleanup(conn.close)
        conn.execute("PRAGMA page_size=4096")
        conn.execute("CREATE TABLE sample(value TEXT)")
        conn.commit()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        before = plain.read_bytes()
        conn.execute("INSERT INTO sample VALUES ('committed in WAL')")
        conn.commit()
        conn.execute("INSERT INTO sample VALUES ('not committed')")
        source = self.root / "encrypted.db"
        source.write_bytes(b"".join(encrypted(before[i:i + PAGE], i // PAGE + 1) for i in range(0, len(before), PAGE)))
        original_wal = Path(str(plain) + "-wal").read_bytes()
        frames = []
        for i in range(32, len(original_wal), PAGE + 24):
            number, size = struct.unpack(">II", original_wal[i:i + 8])
            frames.append((number, size, encrypted(original_wal[i + 24:i + 24 + PAGE], number)))
        Path(str(source) + "-wal").write_bytes(make_wal(frames))
        output = self.root / "decrypted.db"
        crypto.decrypt_database(source, output, KEY)
        reader = connect_readonly(output, immutable=True)
        self.addCleanup(reader.close)
        self.assertEqual([tuple(r) for r in reader.execute("SELECT value FROM sample")], [("committed in WAL",)])
        self.assertEqual(plain.read_bytes(), before)

    def test_plain_database_also_uses_wal_and_shared_reader(self):
        source = self.root / "plain.db"
        conn = sqlite3.connect(source)
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE sample(value TEXT)")
        conn.commit()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO sample VALUES ('new')")
        conn.commit()
        output = self.root / "snapshot.db"
        calls = []

        def shared(path):
            calls.append(path)
            return Path(path).read_bytes()

        crypto.decrypt_database(source, output, None, reader=shared)
        reader = connect_readonly(output, immutable=True)
        self.addCleanup(reader.close)
        self.assertEqual(reader.execute("SELECT value FROM sample").fetchone()[0], "new")
        self.assertIn(str(source) + "-wal", calls)

    def test_bad_key_partial_page_and_wal_keep_previous_output(self):
        plain = self.root / "valid.db"
        with contextlib.closing(sqlite3.connect(plain)) as conn, conn:
            conn.execute("CREATE TABLE sample(value TEXT)")
        data = plain.read_bytes()
        encrypted_data = b"".join(encrypted(data[i:i + PAGE], i // PAGE + 1) for i in range(0, len(data), PAGE))
        source = self.root / "input.db"
        output = self.root / "output.db"
        for case in ("key", "partial", "wal", "btree"):
            with self.subTest(case=case):
                output.write_bytes(b"previous verified output")
                source.write_bytes(encrypted_data[:-1] if case == "partial" else encrypted_data)
                wal_path = Path(str(source) + "-wal")
                wal_path.unlink(missing_ok=True)
                if case == "wal":
                    wal_path.write_bytes(b"invalid WAL")
                if case == "btree":
                    wal_path.write_bytes(make_wal([(2, 2, encrypted(b"\x00" * PAGE, 2))]))
                with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                    crypto.decrypt_database(source, output, b"x" * 16 if case == "key" else KEY)
                self.assertEqual(output.read_bytes(), b"previous verified output")
                self.assertEqual(list(self.root.glob(".wecom-*")), [])

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_decrypted_snapshot_is_private(self):
        source = self.root / "input.db"
        with contextlib.closing(sqlite3.connect(source)) as conn, conn:
            conn.execute("CREATE TABLE sample(value TEXT)")
        output = self.root / "output.db"
        crypto.decrypt_database(source, output, None)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
