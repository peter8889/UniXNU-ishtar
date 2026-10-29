#!/usr/bin/env python3
"""Decompile a DTB, or every entry of an Android dtbo.img, to DTS-like text without dtc (stdlib only).

  scripts/dtb2dts.py ../android_device_xiaomi_ishtar-kernel/dtbs/kalama-v2.dtb > ref/kalama-v2.dts
  scripts/dtb2dts.py ../android_device_xiaomi_ishtar-kernel/dtbs/dtbo.img --list
  scripts/dtb2dts.py ../android_device_xiaomi_ishtar-kernel/dtbs/dtbo.img --entry 7 > ref/dtbo-07.dts

Overlays are printed as-is (fragments, __fixups__); they are not merged into the base.
"""
import argparse
import string
import struct
import sys

PRINTABLE = set(string.printable.encode()) - set(b'\t\n\r\x0b\x0c')


def walk(blob):
    """Yield (depth, 'node', name) / (depth, 'prop', name, value) from a version 16/17 FDT."""
    magic, _, off_struct, off_strings, _, version = struct.unpack_from('>6I', blob)
    if magic != 0xd00dfeed or version < 16:
        sys.exit(f'not an FDT (magic {magic:#x}, version {version})')
    cursor, depth = off_struct, 0
    while True:
        tag, = struct.unpack_from('>I', blob, cursor)
        cursor += 4
        if tag == 1:
            end = blob.index(b'\0', cursor)
            yield depth, 'node', blob[cursor:end].decode() or '/'
            depth += 1
            cursor = (end + 4) & ~3
        elif tag == 2:
            depth -= 1
            yield depth, 'end', None
        elif tag == 3:
            length, name_off = struct.unpack_from('>II', blob, cursor)
            cursor += 8
            name = blob[off_strings + name_off:blob.index(b'\0', off_strings + name_off)].decode()
            yield depth, 'prop', name, blob[cursor:cursor + length]
            cursor = (cursor + length + 3) & ~3
        elif tag == 9:
            return
        elif tag != 4:
            sys.exit(f'bad FDT token {tag} at {cursor - 4:#x}')


def value(data):
    if not data:
        return None
    parts = data[:-1].split(b'\0')
    if data.endswith(b'\0') and all(p and set(p) <= PRINTABLE for p in parts):
        return ', '.join('"%s"' % p.decode() for p in parts)
    if len(data) % 4 == 0:
        return '<%s>' % ' '.join('0x%x' % c for c in struct.unpack(f'>{len(data) // 4}I', data))
    return '[%s]' % data.hex(' ')


def dump(blob, out):
    for depth, kind, *rest in walk(blob):
        pad = '\t' * depth
        if kind == 'node':
            out.write(f'{pad}{rest[0]} {{\n')
        elif kind == 'end':
            out.write(f'{pad}}};\n')
        else:
            v = value(rest[1])
            out.write(f'{pad}{rest[0]};\n' if v is None else f'{pad}{rest[0]} = {v};\n')


def dtbo_entries(blob):
    magic, _, _, entry_size, count, entries_off = struct.unpack_from('>6I', blob)
    if magic != 0xd7b7ab1e:
        return None
    result = []
    for i in range(count):
        size, offset, ident, rev = struct.unpack_from('>4I', blob, entries_off + i * entry_size)
        result.append((ident, rev, blob[offset:offset + size]))
    return result


def model(blob):
    for depth, kind, *rest in walk(blob):
        if kind == 'prop' and depth == 1 and rest[0] in ('model', 'qcom,board-id', 'qcom,msm-id'):
            return value(rest[1])
    return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('image')
    parser.add_argument('--list', action='store_true', help='list dtbo.img entries')
    parser.add_argument('--entry', type=int, help='dtbo.img entry index to decompile')
    args = parser.parse_args()
    blob = open(args.image, 'rb').read()
    entries = dtbo_entries(blob)
    if entries is None:
        return dump(blob, sys.stdout)
    if args.list or args.entry is None:
        for i, (ident, rev, dtb) in enumerate(entries):
            print(f'{i:02d} id={ident:#x} rev={rev:#x} size={len(dtb)} {model(dtb)}')
        return None
    dump(entries[args.entry][2], sys.stdout)
    return None


if __name__ == '__main__':
    main()
