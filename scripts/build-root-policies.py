#!/usr/bin/env python3
"""Sign and verify the OS and SystemOS root policies (docs/HANDOFF.md T5) with UniXNU's VerifiedRoot tools.

Reads the profile [root] values, signs each decrypted raw image with the owner key and checks every block with the
compiled C verifier. Writes <out>/{OS,SystemOS}/{manifest.bin,trusted-key.bin,verification.json}, the layout
build-sheng-source-storage.py reads. Run from the UniXNU checkout.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--unixnu', type=Path, default=Path('.'))
parser.add_argument('--profile', default='ios-27.0.1-24A446')
parser.add_argument('--out', type=Path, required=True, help='e.g. out/<board>/<profile>/<config>/tree/build/verified-root-24A446')
args = parser.parse_args()

root = args.unixnu.resolve()
profile = tomllib.loads((root / f'profiles/os/{args.profile}/profile.toml').read_text())
build = profile['ipsw']['build']
keys = root / 'build/verified-root-host/keys'
library = root / 'build/verified-root-host/verified-root.dylib'
spec = importlib.util.spec_from_file_location('manifest', root / 'kits/VerifiedRoot/tools/manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)

for name, component in (('OS', 'OS'), ('SystemOS', 'Cryptex1,SystemOS')):
    prefix = name.lower()
    uuid, digest = profile['root'][f'{prefix}_volume_uuid'], profile['root'][f'{prefix}_image_sha256']
    member = next(p for p in (root / f'out/ipsw/{build}').glob('*.dmg.json')
                  if json.loads(p.read_text()).get('sha256') == digest)
    image = member.with_suffix('')
    out = args.out / name
    with image.open('rb') as stream:
        record = manifest.make(stream, image.stat().st_size, keys / 'owner.pem', keys / 'owner-public.pem', uuid, 1, out)
    if record['image_sha256'] != digest:
        sys.exit(f'{name}: {image.name} hashes to {record["image_sha256"]}, profile says {digest}')
    subprocess.run([sys.executable, root / 'kits/VerifiedRoot/tools/verify_image.py', '--library', library,
                    '--manifest', out / 'manifest.bin', '--trusted-key', out / 'trusted-key.bin', '--image', image,
                    '--volume-uuid', uuid, '--minimum-generation', '1', '--output', out / 'verification.json'], check=True)
    print(name, image.name, uuid, digest)
