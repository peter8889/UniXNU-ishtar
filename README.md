# UniXNU ishtar

Device support for Xiaomi 13 Ultra, codename `ishtar`, with Qualcomm SM8550.
The device profile selects
[UniXNU-sm8550-common](https://github.com/UniXNU/UniXNU-sm8550-common) and the
`ipados-17.7.11-21H461` OS profile in UniXNU. The board reuses the `sheng` kit,
so the archive plan, ADT generator and package scripts are shared with the
SM8550 reference board.

## State

Kernel, payload and boot image all build, and the assembled image passes its
own round-trip check. Nothing has been loaded on ishtar hardware yet.

| Area | State |
| --- | --- |
| Configuration, firmware, CPU, memory, image assembly, diagnostics | Implemented |
| Storage, display, input, GPU, network, audio, power | Not started |

Storage and display are described in the device tree but compiled out. The GPU
links against stubs. The touch firmware is pinned but the driver is not
selected. See [porting.toml](porting.toml) for the inputs, findings and
completion criteria behind each entry.

## Structure

| Path | Contents |
| --- | --- |
| `porting.toml` | Subsystem inputs, findings, evidence and completion criteria |
| `board.toml` | Device configuration and component selection |
| `feeds.toml` | Pinned SoC source |
| `configs/gpu_defconfig` | Board kernel settings |
| `configs/bringup_defconfig` | Every optional component disabled, for early entry work |
| `dts/ishtar.dts` | Memory, reserved regions and peripheral enablement |
| `patches/xnu/series` | Board patches |
| `proprietary-files.txt` | Firmware input paths |
| `package/` | Device policy and diagnostics |
| `drivers/MiniDisplay/` | Framebuffer and surface implementation, not wired into the build |
| `scripts/` | Device build and inspection tools |

`configs/sheng_defconfig` is inherited from the reference board and is kept as a
comparison point. The board builds with `gpu_defconfig`; `board.toml` names it.

`Adreno740` is selected with `Sm8550Platform`, `AdrenoPM4`, `AdrenoFirmware` and
`ArmSmmu4K`, but the kernel link uses
`build/adreno-link-stubs/libAdrenoLinkStubs.a`. The full driver needs the
payload-stage accelerator ABI and the kernel link has no archive variable for
it, so `scripts/build-adreno-link-stubs.py` supplies the stubs instead.

`ShengUfs`, `VirtioMmioBlock` and `VerifiedRoot` are selected while
`CONFIG_XNU_NATIVE_UFS` stays off, which keeps the hardware description complete
so enabling storage is a configuration change rather than a device-tree change.
The same applies to display: `dts/ishtar.dts` enables `ufs`, `ufsphy`, `gpu`,
`gmu` and `gpu_smmu`, while `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` and
`CONFIG_XNU_NATIVE_MOBILE_DISPLAY` remain off.

The only display output that works without a driver is the direct framebuffer
path in `board.toml`: `panic_framebuffer` at `0xb8000000`, 1440x3200, 5760-byte
stride. Panic screen and boot progress both write through it.

`drivers/MiniDisplay/` holds a framebuffer and surface implementation that no
archive builds yet. It has no archive entry, no `bsd_init` hook and no
configuration switch, so it is inert until those are added.

## Development record

Maintain [porting.toml](porting.toml) with every subsystem change. It records
hardware, configuration, procedures, findings, evidence and completion criteria.
Maintainers and agents follow the [record guide](https://unixnu.com/porting/records).
The `Porting record` CI check validates structure, component coverage and
updates to findings or evidence for changed code.

Shared components come from the selected profiles and the UniXNU catalog. Read
the [UFS guide](https://unixnu.com/porting/ufs) before changing storage
resources or policy.

## Build

The firmware must embed UniXNU, UniXNUDxe, DarwinBoot and the shared
`UniXNURamDiskDxe`, with DiskIoDxe and FAT support. These modules expose the
payload configuration and its boot entries. The board package is
`Platforms/Xiaomi/ishtarPkg` inside the sheng firmware tree. Follow
[firmware integration](https://unixnu.com/porting/uefi-firmware#required-integration).

Run these commands from the UniXNU checkout:

```sh
./unixnu defconfig gpu_defconfig --device ../UniXNU-ishtar
./unixnu fetch --device ../UniXNU-ishtar
./unixnu status --device ../UniXNU-ishtar --json
./unixnu tree --device ../UniXNU-ishtar
./unixnu kernel --device ../UniXNU-ishtar
./unixnu firmware --device ../UniXNU-ishtar --uefi ../uefi-sheng
./unixnu payload --device ../UniXNU-ishtar
./unixnu bootimg --device ../UniXNU-ishtar --uefi ../uefi-sheng --dtb /path/to/firmware.dtb
```

Outputs are under `out/ishtar/ipados-17.7.11-21H461/gpu/`.
The payload step compiles the hardware DTS and writes `kernel.macho.adt`.
The boot image takes the firmware's FDT with `--dtb`.

Build inputs include the selected kernelcache, the firmware DTB, vendor firmware
and UEFI source. Keep binary inputs in local caches. `proprietary-files.txt`
records the firmware inventory against an upstream commit.

The kernel build has one known flake: the clang frontend occasionally crashes on
`osfmk/vm/vm_kern.c` and writes a truncated `.o.json`. Re-running that single
translation unit clears it. A replay must keep `-MJ` and must carry
`-DXNU_BOOT_PROGRESS=1`, or the console hooks compile to no-ops without any
error.

## Documentation

The documentation site is maintained in UniXNU:

- [Device page](https://unixnu.com/devices/ishtar)
- [Building](https://unixnu.com/building)
- [Device repository specification](https://unixnu.com/porting/device-repository)
- [Device-tree specification](https://unixnu.com/porting/device-tree)
- [Component catalog](https://unixnu.com/reference/components)
- [Migration](https://unixnu.com/porting/migration)

Report build results and device boot, storage, display, input, and GPU
observations separately, with source revisions and commands.

## Local build inputs

Save device paths and boot arguments in `unixnu.local.toml` in the UniXNU
checkout. See the [configuration reference](https://unixnu.com/reference/configuration#local-build-inputs).
Argument changes require rebuilding the payload and boot image. See
[boot arguments](https://unixnu.com/xnu/boot-arguments#apply-arguments)
and [green-bar diagnosis](https://unixnu.com/guide/debugging#green-bar).
