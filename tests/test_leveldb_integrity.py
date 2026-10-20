import struct
import unittest

from native_leveldb import validate_log, validate_block, masked_crc


def physical(kind, data):
    return struct.pack('<IHB', masked_crc(bytes([kind]) + data), len(data), kind) + data


class IntegrityTests(unittest.TestCase):
    def test_valid_full_and_fragmented_records(self):
        validate_log(physical(1, b'full') + physical(2, b'first') + physical(4, b'last'))

    def test_wrong_crc_fails(self):
        data = bytearray(physical(1, b'full'))
        data[0] ^= 1
        with self.assertRaises(ValueError):
            validate_log(bytes(data))

    def test_partial_fragment_or_short_payload_fails(self):
        for data in [physical(1, b'old') + physical(2, b'new'),
                     physical(1, b'full')[:-1], physical(4, b'no first')]:
            with self.assertRaises(ValueError):
                validate_log(data)

    def test_sst_block_checks_crc_and_compression(self):
        from types import SimpleNamespace
        data = b'block'
        block = SimpleNamespace(data=data, footer=b'\0' + struct.pack('<I', masked_crc(data+b'\0')))
        validate_block(block)
        block.footer = b'\0' + b'\0'*4
        with self.assertRaises(ValueError):
            validate_block(block)

    def test_oversized_snappy_length_rejected_before_decompression(self):
        from types import SimpleNamespace
        data = b'\x80\x80\x80\x80\x01'
        block = SimpleNamespace(data=data, footer=b'\1' + struct.pack('<I', masked_crc(data+b'\1')))
        with self.assertRaises(ValueError):
            validate_block(block)
