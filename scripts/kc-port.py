#!/usr/bin/env python3
"""Port original-kernelcache addresses from one 24A446 fileset to another (iPad17,3 -> iPhone17,2).

Kexts in two kernelcaches of the same build are the same binaries linked at different addresses, so an address is
ported as (fileset entry, segment, offset) and then verified: code by a window of instructions with branch, ADRP and
page-offset immediates masked; data by bytes, with chained pointers compared by key, diversity and ported target.
If the offset check fails, the masked code window is searched in the same entry and segment and must match once.

  scripts/kc-port.py OLD_KC NEW_KC 0xfffffe00092551ac ...           # print ported addresses
  scripts/kc-port.py OLD_KC NEW_KC --record in.json --out out.json  # port every address in a JSON record

Kernelcaches: out/ios-identity*/kernelcache.decompressed (scripts/ios-identity.py).
"""
import argparse
import hashlib
import json
import re
import struct
import sys

WINDOW = 16
ADDRESS = re.compile(r'^0xfffffe[0-9a-f]{10}$')


class Fileset:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.segments = []   # (name, vmaddr, vmsize, fileoff) of the collection
        self.entries = {}    # entry id -> {segment name: (vmaddr, vmsize)}
        for cmd, at in self.commands(0):
            if cmd == 0x19:
                name, vm, vs, fo = self.segment(at)
                self.segments.append((name, vm, vs, fo))
            elif cmd == 0x80000035:
                _, fo, name_at = struct.unpack_from('<QQI', self.data, at + 8)
                ident = self.data[at + name_at:self.data.index(b'\0', at + name_at)].decode()
                self.entries[ident] = {n: (vm, vs) for c, a in self.commands(fo) if c == 0x19
                                       for n, vm, vs, _ in [self.segment(a)]}
        self.base = self.segments[0][1]

    def commands(self, header):
        count, = struct.unpack_from('<I', self.data, header + 16)
        at = header + 32
        for _ in range(count):
            cmd, size = struct.unpack_from('<II', self.data, at)
            yield cmd, at
            at += size

    def segment(self, at):
        name = self.data[at + 8:at + 24].rstrip(b'\0').decode()
        vm, vs, fo, _ = struct.unpack_from('<4Q', self.data, at + 24)
        return name, vm, vs, fo

    def offset(self, va):
        for _, vm, vs, fo in self.segments:
            if vm <= va < vm + vs:
                return fo + va - vm
        raise ValueError(f'{va:#x} is outside the fileset')

    def word(self, va, size=4):
        return int.from_bytes(self.data[self.offset(va):self.offset(va) + size], 'little')

    def locate(self, va):
        hits = [(ident, seg, va - vm) for ident, segs in self.entries.items() for seg, (vm, vs) in segs.items()
                if vm <= va < vm + vs and seg != '__LINKEDIT']
        if len(hits) != 1:
            raise ValueError(f'{va:#x} is in {len(hits)} entry segments')
        return hits[0]

    def chained(self, va):
        """(target VA, diversity, address diversity, key) of an authenticated kernel-cache chained pointer, else None."""
        raw = self.word(va, 8)
        if not raw >> 63:
            return None
        return self.base + (raw & 0x3fffffff), (raw >> 32) & 0xffff, (raw >> 48) & 1, (raw >> 49) & 3


def masked(fileset, va, count):
    """Instruction words from va with link-time immediates cleared."""
    words, pages = [], set()
    for i in range(count):
        ins = fileset.word(va + 4 * i)
        mask = 0xffffffff
        if ins & 0x7c000000 == 0x14000000:                       # B, BL
            mask = 0xfc000000
        elif ins & 0xff000010 == 0x54000000 or ins & 0x7e000000 == 0x34000000 or ins & 0x3b000000 == 0x18000000:
            mask = ~0x00ffffe0 & 0xffffffff                      # B.cond, CBZ/CBNZ, LDR literal
        elif ins & 0x7e000000 == 0x36000000:                     # TBZ/TBNZ
            mask = ~0x0007ffe0 & 0xffffffff
        elif ins & 0x1f000000 == 0x10000000:                     # ADR/ADRP
            mask = ~0x60ffffe0 & 0xffffffff
            pages.add(ins & 31)
        elif (ins & 0x7f800000 == 0x11000000 or ins & 0x3b000000 == 0x39000000) and (ins >> 5) & 31 in pages:
            mask = ~0x003ffc00 & 0xffffffff                      # ADD imm / LDR-STR imm12 on an ADRP page
        words.append(ins & mask)
    return words


def port(old, new, va, memo):
    if va in memo:
        return memo[va]
    ident, seg, delta = old.locate(va)
    if ident not in new.entries or seg not in new.entries[ident]:
        raise ValueError(f'{va:#x}: {ident} {seg} is missing in the new fileset')
    start, size = new.entries[ident][seg]
    guess = start + delta
    memo[va] = (guess, 'offset')   # set first: vtables and their functions reference each other
    try:
        if 'TEXT_EXEC' in seg:
            count = min(WINDOW, (old.entries[ident][seg][1] - delta) // 4)
            want = masked(old, va, count)
            if masked(new, guess, count) != want:
                hits = [start + o for o in range(0, size - 4 * count, 4)
                        if new.word(start + o) & 0xffff == want[0] & 0xffff and masked(new, start + o, count) == want]
                if len(hits) != 1:
                    raise ValueError(f'{va:#x}: {ident} {seg}+{delta:#x} not verified ({len(hits)} search hits)')
                memo[va] = (hits[0], 'search')
        else:
            for i in range(0, min(64, size - delta), 8):
                a, b = old.chained(va + i), new.chained(guess + i)
                if (a is None) != (b is None) or (a is None and old.word(va + i, 8) != new.word(guess + i, 8)):
                    raise ValueError(f'{va:#x}: data at {ident} {seg}+{delta + i:#x} differs')
                if a is None:
                    continue
                if a[1:] != b[1:]:
                    raise ValueError(f'{va:#x}: pointer at +{i:#x} differs')
                # The kernel is compiled per SoC, so its code is not comparable; key and diversity are.
                if old.locate(a[0])[0] == 'com.apple.kernel':
                    if new.locate(b[0])[0] != 'com.apple.kernel':
                        raise ValueError(f'{va:#x}: pointer at +{i:#x} leaves the kernel')
                elif port(old, new, a[0], memo)[0] != b[0]:
                    raise ValueError(f'{va:#x}: pointer at +{i:#x} differs')
    except ValueError:
        del memo[va]
        raise
    return memo[va]


def vtable_slots(old, new, vtable, slots, memo, problems):
    """[target, diversity] slots read from the ported vtable.

    A slot must carry the same diversity in both filesets; the record's own diversity is kept, since reviewed records
    override some (sheng's legacy-display gives pure-virtual slots the diversity their callers authenticate with).
    """
    try:
        base = port(old, new, vtable, memo)[0]
    except ValueError as error:
        problems.append(str(error))
        return slots
    result = []
    for index, (target, diversity) in enumerate(slots):
        before, entry = old.chained(vtable + 8 * index), new.chained(base + 8 * index)
        if entry is None or before is None or entry[1:] != before[1:]:
            problems.append(f'vtable {vtable:#x} slot {index}: pointers differ')
            result.append([target, diversity])
            continue
        result.append([f'{entry[0]:#x}', diversity])
    return result


def port_record(old, new, value, memo, problems):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == 'kernelcache_sha256':
                result[key] = new.sha256
            elif key == 'slots' and 'vtable' in value and isinstance(item, list) and \
                    all(isinstance(s, list) and len(s) == 2 for s in item):
                result[key] = vtable_slots(old, new, int(value['vtable'], 16), item, memo, problems)
            elif key == 'collection_slide':
                # XnuPrelink rebases the collection to XNU's link address: slide = link base - collection base.
                result[key] = f'{(old.base + int(item, 16) - new.base) & (1 << 64) - 1:#x}'
            elif key == 'evidence' and isinstance(item, str):
                result[key] = f'{item} [Addresses in this text are from kernelcache {old.sha256[:8]}; the fields above ' \
                              f'were ported to {new.sha256[:8]} by scripts/kc-port.py.]'
            else:
                result[key] = port_record(old, new, item, memo, problems)
        return result
    if isinstance(value, list):
        return [port_record(old, new, v, memo, problems) for v in value]
    if isinstance(value, str) and ADDRESS.match(value):
        try:
            return f'{port(old, new, int(value, 16), memo)[0]:#x}'
        except ValueError as error:
            problems.append(str(error))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('old')
    parser.add_argument('new')
    parser.add_argument('addresses', nargs='*')
    parser.add_argument('--record')
    parser.add_argument('--out')
    args = parser.parse_args()
    old, new, memo = Fileset(args.old), Fileset(args.new), {}
    failed = 0
    for text in args.addresses:
        va = int(text, 16)
        try:
            target, how = port(old, new, va, memo)
            ident, seg, delta = old.locate(va)
            print(f'{va:#x} -> {target:#x}  {how:6} {ident} {seg}+{delta:#x}')
        except ValueError as error:
            failed += 1
            print(f'{va:#x} -> FAIL {error}')
    if args.record:
        problems = []
        record = port_record(old, new, json.load(open(args.record)), memo, problems)
        for problem in problems:
            print('FAIL', problem)
        if args.out:
            open(args.out, 'w').write(json.dumps(record, indent=1) + '\n')
        counts = {how: sum(1 for _, h in memo.values() if h == how) for how in ('offset', 'search')}
        print(f'{args.record}: {len(memo)} addresses ported {counts}, {len(problems)} failed')
        failed += len(problems)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
