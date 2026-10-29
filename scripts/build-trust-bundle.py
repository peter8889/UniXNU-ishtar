#!/usr/bin/env python3
"""Bundle the two unchanged Apple trust-cache modules of an IPSW (docs/HANDOFF.md T6).

The generic form of UniXNU's build-original-system-trust.py (pinned to iPad7,1 21H461): reads the StaticTrustCache
('trst') and Cryptex1,SystemTrustCache ('trcs') IM4Ps that `unixnu ipsw fetch` extracted, and writes the
count/offsets/modules bundle DarwinBoot's ValidTrustCaches accepts. Run from the UniXNU checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ipsw-cache', type=Path, default=Path('out/ipsw/24A446'))
parser.add_argument('--out', type=Path, default=Path('build/original-static-system-trust'))
args = parser.parse_args()


def der(data, at):
    tag, size = data[at:at + 2]
    at += 2
    if size & 128:
        count = size & 127
        size = int.from_bytes(data[at:at + count], 'big')
        at += count
    if at + size > len(data):
        raise SystemExit('DER exceeds its input')
    return tag, data[at:at + size], at + size


def module(path):
    data = path.read_bytes()
    tag, sequence, end = der(data, 0)
    fields, cursor = [], 0
    while cursor < len(sequence):
        kind, value, cursor = der(sequence, cursor)
        fields.append((kind, value))
    if tag != 0x30 or end != len(data) or [k for k, _ in fields] != [0x16, 0x16, 0x16, 4] or fields[0][1] != b'IM4P':
        raise SystemExit(f'{path.name}: not a trust-cache IM4P')
    body = fields[3][1]
    entries = struct.unpack_from('<I', body, 20)[0]
    if struct.unpack_from('<I', body)[0] != 2 or len(body) != 24 + entries * 24:
        raise SystemExit(f'{path.name}: not a complete version-2 module')
    hashes = [body[24 + 24 * i:44 + 24 * i] for i in range(entries)]
    # DarwinBoot and the kernel binary-search each module: CDHashes strictly ascending, hash type 1-4.
    if hashes != sorted(set(hashes)) or not all(1 <= body[44 + 24 * i] <= 4 for i in range(entries)):
        raise SystemExit(f'{path.name}: entries are not in loader order')
    return fields[1][1], body


found = {kind: (path, body) for path in sorted(args.ipsw_cache.glob('*.trustcache'))
         for kind, body in [module(path)]}
if set(found) != {b'trst', b'trcs'}:
    raise SystemExit(f'need one StaticTrustCache (trst) and one SystemTrustCache (trcs), found {sorted(found)}')
static, system = found[b'trst'][1], found[b'trcs'][1]
bundle = struct.pack('<3I', 2, 12, 12 + len(static)) + static + system
args.out.mkdir(parents=True, exist_ok=True)
(args.out / 'original-static-system.bundle').write_bytes(bundle)
(args.out / 'inputs.json').write_text(json.dumps(dict(
    static=found[b'trst'][0].name, original_static_sha256=hashlib.sha256(static).hexdigest(),
    system=found[b'trcs'][0].name, original_system_sha256=hashlib.sha256(system).hexdigest(),
    bundle_sha256=hashlib.sha256(bundle).hexdigest(), own_code_entries_added=False, original_modules_modified=False),
    indent=2) + '\n')
print('bundled', found[b'trst'][0].name, found[b'trcs'][0].name, hashlib.sha256(bundle).hexdigest())
