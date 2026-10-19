import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_support.local_io import atomic_output
from native_support import wal_snapshot


class NativeIOTests(unittest.TestCase):
    def test_concurrent_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'export.md'
            with self.assertRaises(FileExistsError):
                with atomic_output(path, overwrite=False) as stream:
                    stream.write('our export')
                    path.write_text('concurrent export')
            self.assertEqual(path.read_text(), 'concurrent export')
            self.assertEqual(list(Path(directory).glob('.wecom-*')), [])

    def test_new_output_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'export.md'
            with atomic_output(path, overwrite=False) as stream:
                stream.write('original transcript')
            self.assertEqual(path.read_text(), 'original transcript')

    def test_same_metadata_does_not_hide_changing_contents(self):
        counter = 0
        def changing(path):
            nonlocal counter
            if path.endswith('-wal'):
                raise FileNotFoundError(path)
            counter += 1
            return bytes([counter]) * 4096
        with patch.object(wal_snapshot, '_metadata', return_value=(4096, 1, 1)):
            with self.assertRaisesRegex(ValueError, 'changed'):
                wal_snapshot.read_snapshot('synthetic.db', reader=changing)

    def test_stable_contents_are_accepted(self):
        def stable(path):
            if path.endswith('-wal'):
                raise FileNotFoundError(path)
            return b'a' * 4096
        with patch.object(wal_snapshot, '_metadata', return_value=(4096, 1, 1)):
            self.assertEqual(wal_snapshot.read_snapshot('synthetic.db', reader=stable), b'a' * 4096)
