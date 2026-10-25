#!/usr/bin/env python3
"""Local stubs for the display handoff and boot-log imports of the Adreno user client.

The Adreno740 publish object imports three symbols owned by the display and boot-progress
components:

  native_gop_handoff_call    GopFramebuffer late archive
  native_gop_handoff_memory  GopFramebuffer late archive
  boot_log_export_put        BootProgress archive

Neither archive can be built here: build-gop-framebuffer.py / build-gop-legacy-display.py
require the qualified prelink candidates (build/xnu-prelink/*.macho with pinned sha256) and
build-boot-progress.py is only linked when XNU_BOOT_PROGRESS=1. Until those inputs exist, the
kernel links against real returning stubs so the GMU bring-up path can be validated:

  * boot_log_export_put returns -1, so the export path reports "not stored" and is skipped.
  * native_gop_handoff_call returns kIOReturnUnsupported; the two handoff calls only run from
    the Adreno user client (Metal handoff), never during GMU bring-up.
  * native_gop_handoff_memory returns NULL, which the caller already checks.

Absolute-zero definitions cannot be used: the compiler emits a direct branch, and a branch to
address 0 is out of the ARM64 +/-128 MB range. Remove this archive from
CONFIG_XNU_EXTRA_LD_ARCHIVES as soon as the real display archive is linked.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/adreno-link-stubs'
OUT.mkdir(parents=True, exist_ok=True)
STUBS = OUT / 'adreno-link-stubs.S'
STUBS.write_text(''.join([
    '.text\n',
    '.p2align 2\n',
    # int boot_log_export_put(uint32_t, uint32_t, uint32_t, const void *, uint32_t)
    '.globl _boot_log_export_put\n',
    '_boot_log_export_put:\n',
    '    mov w0, #-1\n',
    '    ret\n',
    # IOReturn native_gop_handoff_call(uint32_t, task_t, const void *, size_t, void *, size_t)
    '.globl _native_gop_handoff_call\n',
    '_native_gop_handoff_call:\n',
    '    mov w0, #0x2c7\n',          # low half of kIOReturnUnsupported
    '    movk w0, #0xe000, lsl #16\n',
    '    ret\n',
    # IOMemoryDescriptor *native_gop_handoff_memory(void)
    '.globl _native_gop_handoff_memory\n',
    '_native_gop_handoff_memory:\n',
    '    mov x0, #0\n',
    '    ret\n',
]))
obj = OUT / 'adreno-link-stubs.o'
subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-Wno-incompatible-sysroot',
                '-c', STUBS, '-o', obj], check=True)
archive = OUT / 'libAdrenoLinkStubs.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', archive, obj], check=True)
defined = subprocess.run(['xcrun', 'nm', '-g', archive], capture_output=True, text=True).stdout
missing = [name for name in ('_native_gop_handoff_call', '_native_gop_handoff_memory',
                             '_boot_log_export_put') if (' T ' + name) not in defined]
if missing:
    raise SystemExit('Stub definitions absent: ' + ', '.join(missing))
print('PASS: 3 returning display/boot-log stubs archived; remove once the display ABI is qualified')
