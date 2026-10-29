#!/usr/bin/env python3
"""Read the identity inputs of the iOS 27 donor IPSW without downloading it (HTTP range requests).

  python3 scripts/ios-identity.py [--unixnu ../UniXNU] [--product iPhone17,2] [--build 24A446] [--out out/ios-identity]

Writes to --out: BuildManifest summary (manifest.json), the decoded Apple device tree (devicetree.txt, product.json) and
the decompressed arm64e kernelcache (kernelcache.decompressed, sha256 in manifest.json). Uses UniXNU's range reader and
macOS /usr/bin/compression_tool; nothing to install.
"""
import argparse
import hashlib
import json
import plistlib
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# Properties the profile's [adt] tables copy (product node, display and identity values SpringBoard reads).
PRODUCT_KEYS = ('product', 'display', 'buttons', 'defaults', 'chosen', 'disp0', 'dcp', 'multi-touch')


def read_adt(blob, at=0, parent=None):
    """Return ([(path, {property: raw})], end offset) for an Apple device tree, depth first."""
    nprops, nchildren = struct.unpack_from('<II', blob, at)
    at += 8
    props = {}
    for _ in range(nprops):
        name = blob[at:at + 32].split(b'\0')[0].decode()
        size, = struct.unpack_from('<I', blob, at + 32)
        size &= 0x7fffffff
        props[name] = blob[at + 36:at + 36 + size]
        at += 36 + ((size + 3) & ~3)
    name = props.get('name', b'?').rstrip(b'\0').decode()
    here = '/' if parent is None else parent.rstrip('/') + '/' + name
    nodes = [(here, props)]
    for _ in range(nchildren):
        children, at = read_adt(blob, at, here)
        nodes += children
    return nodes, at


def unpack(payload, scratch):
    """An IM4P payload, LZFSE-decoded (bvx2) by macOS compression_tool when compressed."""
    if payload[:3] != b'bvx':
        return payload
    packed, raw = scratch.with_suffix('.lzfse'), scratch.with_suffix('.raw')
    packed.write_bytes(payload)
    subprocess.run(['/usr/bin/compression_tool', '-decode', '-a', 'lzfse', '-i', packed, '-o', raw], check=True)
    packed.unlink()
    data = raw.read_bytes()
    raw.unlink()
    return data


def show(raw):
    text = raw.rstrip(b'\0')
    if text and all(32 <= c < 127 or c == 0 for c in text):
        parts = [p.decode() for p in text.split(b'\0')]
        return parts[0] if len(parts) == 1 else parts
    if len(raw) == 4:
        return struct.unpack('<I', raw)[0]
    if len(raw) == 8:
        return struct.unpack('<Q', raw)[0]
    return raw.hex()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--unixnu', default=str(Path(__file__).resolve().parents[2] / 'UniXNU'))
    parser.add_argument('--product', default='iPhone17,2')
    parser.add_argument('--build', default='24A446')
    parser.add_argument('--out', default='out/ios-identity')
    parser.add_argument('--no-kernel', action='store_true', help='skip the kernelcache (about 60 MiB of range reads)')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.unixnu) / 'scripts'))
    from unixnu.ipsw import RangeFile, im4p_payload

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    device = json.load(urllib.request.urlopen(f'https://api.ipsw.me/v4/device/{args.product}?type=ipsw'))
    firmware = next(f for f in device['firmwares'] if f['buildid'] == args.build)
    archive = zipfile.ZipFile(RangeFile(firmware['url']))
    manifest = plistlib.loads(archive.read('BuildManifest.plist'))
    # Multi-device IPSWs (iPad17,1-4) carry one identity per board: pick this product's.
    board = device['boards'][0]['boardconfig'].lower()
    identity = next(i for i in manifest['BuildIdentities']
                    if i['Info']['RestoreBehavior'] == 'Erase' and i['Info']['DeviceClass'] == board)
    members = {k: v['Info']['Path'] for k, v in identity['Manifest'].items() if 'Info' in v and 'Path' in v['Info']}
    summary = {'url': firmware['url'], 'ipsw_sha256': firmware.get('sha256sum'), 'product': args.product,
               'version': manifest['ProductVersion'], 'build': manifest['ProductBuildVersion'],
               'device_class': identity['Info']['DeviceClass'], 'chip_id': int(identity['ApChipID'], 16),
               'board_id': int(identity['ApBoardID'], 16), 'members': members}

    tree = unpack(im4p_payload(archive.read(members['DeviceTree'])), out / 'devicetree')
    nodes, _ = read_adt(tree)
    with (out / 'devicetree.txt').open('w') as listing:
        for path, props in nodes:
            listing.write(f'{path}\n')
            for name, raw in props.items():
                listing.write(f'  {name} = {show(raw)!r}\n')
    picked = {path: {k: show(v) for k, v in props.items()} for path, props in nodes
              if path.rsplit('/', 1)[-1] in PRODUCT_KEYS or path == '/'}
    (out / 'product.json').write_text(json.dumps(picked, indent=1) + '\n')

    if not args.no_kernel:
        data = unpack(im4p_payload(archive.read(members['KernelCache'])), out / 'kernelcache')
        (out / 'kernelcache.decompressed').write_bytes(data)
        if data[:4] != b'\xcf\xfa\xed\xfe':
            sys.exit('kernelcache is not a thin 64-bit Mach-O; handle the fat case as UniXNU ipsw.kernelcache() does')
        summary['kernelcache_sha256'] = hashlib.sha256(data).hexdigest()
        at = data.find(b'Darwin Kernel Version')
        summary['kernel_version'] = data[at:data.index(b'\0', at)].decode() if at >= 0 else None
    (out / 'manifest.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'members'}, indent=1))


if __name__ == '__main__':
    main()
