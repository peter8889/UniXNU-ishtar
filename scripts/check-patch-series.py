#!/usr/bin/env python3
"""Dry-run the resolved XNU patch order on a scratch copy of the pinned XNU source.

  ~/miniconda3/bin/python3 scripts/check-patch-series.py --unixnu ../UniXNU --xnu ../ref-src/xnu-12377

--xnu is any clone of apple-oss-distributions/xnu; the profile's xnu_revision is checked out in a --shared scratch
clone (out/patch-check), so the source clone is not modified. Prints one line per patch and exits 1 on a failure.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--unixnu', type=Path, default=DEVICE.parent / 'UniXNU')
    parser.add_argument('--xnu', type=Path, required=True)
    args = parser.parse_args()
    status = json.loads(subprocess.check_output([sys.executable, 'unixnu', 'status', '--json', '-D', str(DEVICE)],
                                                cwd=args.unixnu))
    revision = status['board']['os']['xnu_revision']
    work = DEVICE / 'out/patch-check'
    shutil.rmtree(work, ignore_errors=True)
    subprocess.run(['git', 'clone', '-q', '--shared', '--no-checkout', str(args.xnu.resolve()), str(work)], check=True)
    subprocess.run(['git', '-C', str(work), '-c', 'advice.detachedHead=false', 'checkout', '-q', revision], check=True)
    failed = 0
    for patch in status['patch_order']:
        result = subprocess.run(['git', '-C', str(work), 'apply', patch], capture_output=True, text=True)
        failed += result.returncode != 0
        print(f"{'ok  ' if result.returncode == 0 else 'FAIL'} {Path(patch).parent.name}/{Path(patch).name}"
              + (f": {result.stderr.strip().splitlines()[0]}" if result.returncode else ''))
    print(f'{len(status["patch_order"]) - failed}/{len(status["patch_order"])} applied on {revision}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
