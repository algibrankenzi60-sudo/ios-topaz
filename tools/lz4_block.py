#!/usr/bin/env python3
"""Small greedy LZ4 block encoder for the recovery ramdisk container."""
import argparse
from pathlib import Path

def _emit_length(out, length):
    while length >= 255:
        out.append(255)
        length -= 255
    out.append(length)


def compress(data):
    size = len(data)
    out = bytearray()
    table = {}
    anchor = 0
    pos = 0
    while pos + 12 <= size:
        word = int.from_bytes(data[pos:pos + 4], 'little')
        key = ((word * 2654435761) & 0xffffffff) >> 16
        ref = table.get(key, -1)
        table[key] = pos
        if ref < 0 or pos - ref > 0xffff or data[ref:ref + 4] != data[pos:pos + 4]:
            pos += 1
            continue

        match_end = pos + 4
        ref_end = ref + 4
        while match_end < size - 5 and data[match_end] == data[ref_end]:
            match_end += 1
            ref_end += 1

        literal_len = pos - anchor
        match_len = match_end - pos
        token_pos = len(out)
        out.append(0)
        out[token_pos] = (min(literal_len, 15) << 4) | min(match_len - 4, 15)
        if literal_len >= 15:
            _emit_length(out, literal_len - 15)
        out.extend(data[anchor:pos])
        out.extend((pos - ref).to_bytes(2, 'little'))
        if match_len - 4 >= 15:
            _emit_length(out, match_len - 4 - 15)

        old_pos = pos
        pos = match_end
        anchor = pos
        for update in range(old_pos + 1, min(pos, size - 11)):
            word = int.from_bytes(data[update:update + 4], 'little')
            key = ((word * 2654435761) & 0xffffffff) >> 16
            table[key] = update

    literal_len = size - anchor
    out.append(min(literal_len, 15) << 4)
    if literal_len >= 15:
        _emit_length(out, literal_len - 15)
    out.extend(data[anchor:])
    return bytes(out)


def decompress(data, expected_size):
    """Host-side reference decoder used by packaging and tests."""
    out = bytearray()
    ip = 0
    while ip < len(data):
        token = data[ip]
        ip += 1
        literals = token >> 4
        if literals == 15:
            while True:
                part = data[ip]
                ip += 1
                literals += part
                if part != 255:
                    break
        if ip + literals > len(data):
            raise ValueError('truncated LZ4 literals')
        out.extend(data[ip:ip + literals])
        ip += literals
        if ip == len(data):
            break
        if ip + 2 > len(data):
            raise ValueError('truncated LZ4 offset')
        offset = data[ip] | (data[ip + 1] << 8)
        ip += 2
        if not offset or offset > len(out):
            raise ValueError('invalid LZ4 offset')
        match = token & 15
        if match == 15:
            while True:
                part = data[ip]
                ip += 1
                match += part
                if part != 255:
                    break
        match += 4
        for _ in range(match):
            out.append(out[-offset])
        if len(out) > expected_size:
            raise ValueError('LZ4 output exceeds expected size')
    if len(out) != expected_size:
        raise ValueError('LZ4 output size mismatch')
    return bytes(out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    source = args.source.read_bytes()
    packed = compress(source)
    if decompress(packed, len(source)) != source:
        raise SystemExit('internal LZ4 round-trip failed')
    args.output.write_bytes(packed)
    print(f'input_bytes={len(source)} compressed_bytes={len(packed)}')
