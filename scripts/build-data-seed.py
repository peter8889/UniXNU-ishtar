#!/usr/bin/env python3
"""Make the small packed APFS Data seed (docs/HANDOFF.md T7) from the OS image's initial private/var.

The generic form of UniXNU's prepare-owner-data-fixture.py (pinned to the iPad7,1 OS mount): attaches the profile's
decrypted OS image read-only, copies private/var the same way into a fresh 32 MiB APFS volume, and packs it with
DarwinBoot's packed_ramdisk (DBRDISK1). Prints the volume UUID for CONFIG_XNU_OWNER_DATA_VOLUME_UUID.
Run from the UniXNU checkout; grow the result with scripts/seed-data-grow.py once the userdata image exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', default='ios-27.0.1-24A446')
parser.add_argument('--out', type=Path, default=Path('build/owner-data-fixture'))
args = parser.parse_args()

root = Path('.').resolve()
sys.path.insert(0, str(root / 'drivers/DarwinBoot/Test'))
import packed_ramdisk

profile = tomllib.loads((root / f'profiles/os/{args.profile}/profile.toml').read_text())
digest = profile['root']['os_image_sha256']
os_image = next(p for p in (root / f'out/ipsw/{profile["ipsw"]["build"]}').glob('*.dmg.json')
                if json.loads(p.read_text()).get('sha256') == digest).with_suffix('')
out = args.out.resolve()
raw, packed = out / 'owner-data-32.cdr', out / 'owner-data-32.dbr'
if raw.exists() or packed.exists():
    sys.exit(f'refuse to overwrite an existing Data seed in {out}')
out.mkdir(parents=True, exist_ok=True)


def attach(image, mountpoint, *extra):
    entities = plistlib.loads(subprocess.check_output(['hdiutil', 'attach', '-nobrowse', '-owners', 'off', *extra,
                                                       '-mountpoint', str(mountpoint), '-plist', str(image)]))['system-entities']
    if not any(e.get('mount-point') == str(mountpoint) for e in entities):
        sys.exit(f'{image.name} did not mount at {mountpoint}')
    return entities


with tempfile.TemporaryDirectory(dir=out) as scratch:
    source_mount, target = Path(scratch) / 'os', Path(scratch) / 'data'
    source_mount.mkdir()
    target.mkdir()
    attach(os_image, source_mount, '-readonly', '-noverify', '-noautofsck')
    try:
        subprocess.run(['hdiutil', 'create', '-size', '32m', '-layout', 'NONE', '-fs', 'APFS',
                        '-volname', 'OwnerData', '-type', 'UDTO', str(raw)], check=True, capture_output=True)
        entities = attach(raw, target)
        volume = next(e['dev-entry'] for e in entities if e.get('mount-point') == str(target))
        volume_uuid = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', volume]))['VolumeUUID']
        count = total = 0
        source = source_mount / 'private/var'
        try:
            # As prepare-owner-data-fixture.py: everything but staged_system_apps, symlinks kept, runtime dirs added.
            for current, dirs, files in os.walk(source, followlinks=False):
                dirs[:] = [name for name in dirs if name != 'staged_system_apps']
                dest = target / Path(current).relative_to(source)
                dest.mkdir(exist_ok=True)
                os.chmod(dest, stat.S_IMODE(Path(current).stat().st_mode))
                for name in list(dirs) + files:
                    src, dst = Path(current) / name, dest / name
                    if src.is_symlink():
                        os.symlink(os.readlink(src), dst)
                        if name in dirs:
                            dirs.remove(name)
                    elif src.is_file():
                        shutil.copy2(src, dst)
                        count += 1
                        total += src.stat().st_size
            for name in ('keybags', 'mobile/tmp', 'tmp', 'run'):
                (target / name).mkdir(parents=True, exist_ok=True)
            os.chmod(target / 'tmp', 0o1777)
        finally:
            subprocess.run(['hdiutil', 'detach', str(target)], check=True, capture_output=True)
    finally:
        subprocess.run(['hdiutil', 'detach', str(source_mount)], check=True, capture_output=True)

data = raw.read_bytes()
if len(data) != 32 * 1024**2 or data[32:36] != b'NXSB':
    sys.exit('hdiutil did not produce a raw 32 MiB APFS container')
packed_ramdisk.pack(raw, packed)
report = dict(volume_uuid=volume_uuid, os_image=os_image.name, os_image_sha256=digest, raw_sha256=hashlib.sha256(data).hexdigest(),
              packed=packed.name, packed_sha256=hashlib.sha256(packed.read_bytes()).hexdigest(),
              source_regular_files=count, source_regular_bytes=total)
(out / 'seed.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
