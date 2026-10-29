# UniXNU ishtar

iOS 27.0.1 (24A446) on the **Xiaomi 13 Ultra** (`ishtar`, SM8550-AB), presented to iOS as an **iPhone 16 Pro Max**
(`iPhone17,2`, D94AP). Built with [UniXNU](https://github.com/UniXNU/UniXNU) on the xnu-12377 kernel that boots
iPadOS 27 on the sheng tablet (same SoC), with shared [SM8550 support](https://github.com/UniXNU/UniXNU-sm8550-common).

Supersedes the iOS 18 port ([markakash/UniXNU-ishtar-old](https://github.com/markakash/UniXNU-ishtar-old) `79ddf457`,
Bergamota xnu-11215). Its hardware findings carry over; its kernel patches do not (see
[docs/MIGRATION.md](docs/MIGRATION.md)).

**State:** configured and host-checked, not built or booted. Per-area status, findings and next actions:
[porting.toml](porting.toml).

## Inputs

| Input | Where |
| --- | --- |
| UniXNU with the `ios-27.0.1-24A446` profile | `../UniXNU` = [markakash/UniXNU](https://github.com/markakash/UniXNU) `main`: `feat/ipados27-gpu-parity` (87bf1f9) + [unixnu/*.patch](unixnu/) |
| SM8550 shared support | `UniXNU-sm8550-common` 23b2049 (`feeds.toml`); SoC patches for xnu-12377 in `patches/xnu-12377/soc/` |
| sheng device layer | copied from `UniXNU-sheng` `feat/ipados27-gpu-parity` 6ed0ba4: `patches/xnu-12377/`, `package/` |
| iOS | iPhone17,2 27.0.1 24A446 IPSW (URL and pins in the profile) |
| Firmware | `../uefi-ishtar` = UniXNU `uefi-sheng` 20ac23d + [firmware/](firmware/) (`ishtarPkg`); stock DTB/DTBO from AOSPA `android_device_xiaomi_ishtar-kernel` |

## Commands

UniXNU needs Python 3.11+ (`~/miniconda3/bin/python3` here; `/usr/bin/python3` is 3.9). Run from `../UniXNU`:

```sh
git clone https://github.com/markakash/UniXNU ../UniXNU   # or: UniXNU/UniXNU + git am ../UniXNU-ishtar/unixnu/*.patch
PY=~/miniconda3/bin/python3
$PY ./unixnu defconfig ishtar_ios27_defconfig -D ../UniXNU-ishtar
$PY ./unixnu fetch -D ../UniXNU-ishtar     # or local.toml (see local.toml.example)
$PY ./unixnu status --json -D ../UniXNU-ishtar
$PY scripts/porting-record.py check --device ../UniXNU-ishtar
$PY ./unixnu build kernel -D ../UniXNU-ishtar        # needs Xcode iphoneos SDK
$PY ./unixnu build firmware -D ../UniXNU-ishtar --uefi ../uefi-ishtar
$PY ./unixnu build payload -D ../UniXNU-ishtar --unique-chip-id "$ID"   # needs dtc
$PY ./unixnu bootimg -D ../UniXNU-ishtar --uefi ../uefi-ishtar --dtb ../uefi-ishtar/Resources/DTBs/ishtar.dtb
fastboot boot out/ishtar/ios-27.0.1-24A446/ishtar_ios27/boot/boot.img   # nothing is flashed
```

Board tools in this repository (stdlib Python, no installs):

```sh
python3 scripts/dtb2dts.py <dtbo.img> --list                  # decompile stock DTB/DTBO without dtc
python3 scripts/ios-identity.py                               # iPhone17,2 manifest, device tree, kernelcache (HTTP ranges)
$PY scripts/check-patch-series.py --xnu ../ref-src/xnu-12377  # dry-run the 75-patch order
$PY scripts/kc-port.py <iPad kc> <iPhone kc> --record <iPad record> --out abi/<name>-d94ap.json
```

`abi/` holds the iPhone17,2 versions of sheng's and UniXNU's iPad17,3 kernelcache records (ported, 0 failures:
[reports/kc-port-24A446-d94ap.txt](reports/kc-port-24A446-d94ap.txt)); the profile carries the ported
`original-classes.json` and AMFI init address.

## Stages

| Stage | Adds | Blocked on |
| --- | --- | --- |
| 0 | kernel, UFS root, launchd, verbose console | profile `[root]` UUIDs, Data volume UUID, a kernel build |
| 1 | display (`build-gop-legacy-display-27.py`, `offline-legacy-*`) | copying the builder with `abi/legacy-display-24A446-d94ap.json` |
| 2 | touch (FTM5 over GPI) and keys | port of old 2010-2019 (record: `abi/hid-device-24A446-d94ap.json`) |
| 3 | A740 (UniXNU Adreno740/AdrenoMetal) | UniXNU accelerator builder reading `abi/ioaccelerator-base-abi-24A446-d94ap.json` |
| 4 | DPU scaling and 120 Hz, battery, USB Ethernet, Wi-Fi | ports of old 2025, 2035, 2012 |

Running the payload's userdata step writes the iOS images into `userdata` and **erases Android user data**.

## Layout

| Path | Contents |
| --- | --- |
| `board.toml`, `porting.toml` | board configuration (format 2) and the device record |
| `dts/ishtar.dts` | memory, splash reservation, CPU clusters, enabled SoC blocks |
| `configs/ishtar_ios27_defconfig` | stage 0 kernel configuration |
| `patches/xnu-12377/` | device series (sheng) and `soc/` series (SM8550 for 12377) |
| `package/` | board package (appears as `kits/ishtar`) |
| `unixnu/` | UniXNU commit adding the iOS 27 profile |
| `firmware/` | uefi-ishtar commit adding `ishtarPkg` on top of UniXNU's `uefi-sheng` |
| `reports/` | host check outputs |
| `docs/MIGRATION.md` | old ishtar patches 2000-2035 mapped to their new home |
| `docs/HANDOFF.md` | ordered tasks to the first boot, for an agent on a machine with the build tools |

Apple, Qualcomm and Xiaomi binaries are never committed (`.gitignore`); decompiled stock trees go to `ref/`.

## Credits

[UniXNU](https://github.com/UniXNU), the sheng port and UniXNU-sm8550-common; the earlier ishtar iOS 18 port and its
sources (Bergamota, ios-sweet, UniXNU-negroni, uefi-nuwa, Mu-Silicium); AOSPA for the prebuilt ishtar kernel trees.
