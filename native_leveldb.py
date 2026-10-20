"""Fail-closed integrity checks around the vendored LevelDB reader."""
import struct

import google_crc32c

MAX_BLOCK = 16 * 1024 * 1024


def masked_crc(data):
    value = google_crc32c.value(data)
    return (((value >> 15) | (value << 17)) + 0xa282ead8) & 0xffffffff


def validate_log(data):
    fragmented = False
    for start in range(0, len(data), 32768):
        block = data[start:start + 32768]
        pos = 0
        while pos < len(block):
            tail = block[pos:]
            if not any(tail):
                break
            if len(tail) < 7:
                raise ValueError('Truncated LevelDB log header')
            checksum, length, kind = struct.unpack_from('<IHB', tail)
            end = pos + 7 + length
            if end > len(block) or kind not in (1, 2, 3, 4):
                raise ValueError('Invalid LevelDB physical record')
            content = block[pos + 7:end]
            if masked_crc(bytes([kind]) + content) != checksum:
                raise ValueError('LevelDB log checksum mismatch')
            if kind in (1, 2) and fragmented:
                raise ValueError('Unfinished LevelDB logical record')
            if kind in (3, 4) and not fragmented:
                raise ValueError('Missing LevelDB first fragment')
            fragmented = kind in (2, 3)
            pos = end
    if fragmented:
        raise ValueError('Unfinished LevelDB logical record')


def validate_block(block):
    if len(block.footer) != 5 or block.footer[0] not in (0, 1):
        raise ValueError('Unsupported LevelDB block compression')
    if masked_crc(block.data + block.footer[:1]) != int.from_bytes(block.footer[1:], 'little'):
        raise ValueError('LevelDB block checksum mismatch')
    size = len(block.data)
    if block.footer[0] == 1:
        size = 0
        for index, value in enumerate(block.data[:5]):
            size |= (value & 127) << (7 * index)
            if not value & 128:
                break
        else:
            raise ValueError('Invalid Snappy length')
        if not block.data:
            raise ValueError('Empty Snappy block')
    if size > MAX_BLOCK:
        raise ValueError('Decompressed LevelDB block exceeds supported size')


def records_from_file(path):
    from dfindexeddb.leveldb import ldb, log
    if path.suffix == '.log':
        validate_log(path.read_bytes())
        yield from log.FileReader(str(path)).GetParsedInternalKeys()
    else:
        reader = ldb.FileReader(str(path))
        validate_block(reader.index_block)
        for block in reader.GetBlocks():
            validate_block(block)
            yield from block.GetRecords()
