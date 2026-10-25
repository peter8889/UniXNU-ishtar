# Agent instructions

This repository owns ishtar board configuration, peripherals, firmware
selection, partition layout, power policy, and packaging. Shared SM8550
resources and operations belong to `UniXNU-sm8550-common`. The documentation
site, component catalog, and common build tools belong to `UniXNU`. The board
reuses the `sheng` kit, so shared package scripts and the archive plan live
there rather than here.

Read the following before editing:

| Task | Required reading |
| --- | --- |
| Every port | [Porting](https://unixnu.com/porting/), [repository format](https://unixnu.com/porting/device-repository), [component catalog](https://unixnu.com/reference/components) |
| Hardware | [Device trees](https://unixnu.com/porting/device-tree), [matching](https://unixnu.com/drivers/device-tree-matching), selected SoC README and DTSI |
| Components | Selected component README, catalog metadata, build interface, relevant source |
| Kernel | Selected OS profile, XNU source, [patch reference](https://unixnu.com/xnu/source-and-patches), ordered patch series |
| Images | [Prelink](https://unixnu.com/concepts/prelink), [payload](https://unixnu.com/concepts/payload), [UEFI firmware](https://unixnu.com/porting/uefi-firmware) |
| Verification | [Building](https://unixnu.com/building), [bring-up](https://unixnu.com/porting/bring-up) |
| Migration | [Migration guide](https://unixnu.com/porting/migration) |

Search UniXNU's `components.toml` and read existing implementations before
adding a capability. Select components by interface, hardware scope, OS
ABI, and board dependencies. Use canonical component names in sources,
paths, build commands, and dependencies. Preserve source filenames,
runtime classes, bundle IDs, plugin filenames, symbols, and protocol IDs.

Use `dts/ishtar.dts` for board hardware and include the selected SoC DTSI.
Keep GPU votes and signed ZAP firmware inputs with the board. Inspect
`local.toml` and CLI overrides before changing source pins.

Run from the UniXNU checkout:

```sh
./unixnu defconfig gpu_defconfig --device ../UniXNU-ishtar
./unixnu status --device ../UniXNU-ishtar --json
./unixnu tree --device ../UniXNU-ishtar
./unixnu kernel --device ../UniXNU-ishtar
```

Use the README for firmware and payload inputs. Run existing checks
relevant to the change. Report commands, outputs, missing inputs, and
hardware observations separately. Record device boot, storage, display,
input, and GPU checkpoints.

Update relevant English and Chinese site pages in UniXNU. Write concise
English for this repository. Describe current behavior with direct
statements and ordinary punctuation.

## Porting record

Read the device's `porting.toml` and the
[record guide](https://unixnu.com/porting/records) before implementation.
For storage, also read the [UFS guide](https://unixnu.com/porting/ufs).
Update each affected area's findings or evidence with its code change.
The documentation site renders this same record. Follow its schema and
completion levels for both maintainer and agent work.

## Board constraints

The board declares 8 GiB of DRAM, deliberately below the fitted capacity, and
a `no-map` splash reservation at `0xb8000000`. Neither value is a placeholder:
raising the declared DRAM lets the physical aperture reach addresses no DRAM
backs, and mapping the splash region as normal memory lets the page-table
allocator hand the framebuffer out.

`gpu_defconfig` leaves `CONFIG_XNU_NATIVE_UFS`, `CONFIG_XNU_NATIVE_LEGACY_DISPLAY`
and `CONFIG_XNU_NATIVE_MOBILE_DISPLAY` off. The device tree still enables those
nodes so that turning a driver on is a configuration change. Keep that split.

`patches/xnu/series` is intentionally empty: the board carries no XNU patch. A
patch that made `cpu_init()` call `do_cpuid()` on every CPU was removed because
`cpuid_info()` returns the single global `cpuid_cpu_info`, which `do_cpuid()`
fills once on the boot CPU and stamps with `CPU_ARCH_ARMv8`. Secondary CPUs
therefore already see a known architecture, and the extra call only risked a
write into a section that is read-only after the late lockdown. Do not re-add it.
