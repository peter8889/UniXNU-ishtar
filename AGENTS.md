# Agent instructions

This repository owns the ishtar (Xiaomi 13 Ultra, SM8550-AB) board for iOS 27.0.1 24A446 with the iPhone17,2
identity: board configuration, DTS, kernel patch layers, board package, firmware inputs and the porting record.
Shared SM8550 code belongs to `UniXNU-sm8550-common`; build tools, OS profiles and the component catalog to `UniXNU`.

## Before editing

1. Read [porting.toml](porting.toml) (authoritative status, findings, next actions), [README.md](README.md) and,
   to build or boot, [docs/HANDOFF.md](docs/HANDOFF.md) (ordered tasks T1-T11).
2. Read the UniXNU guides: [device repository](https://unixnu.com/porting/device-repository),
   [records](https://unixnu.com/porting/records), [device tree](https://unixnu.com/porting/device-tree),
   [arm64e](https://unixnu.com/porting/arm64e), and the component docs in `../UniXNU/docs/drivers/`.
3. For a hardware fact, check the old iOS 18 port first (`../ishtar`, PORTING.md and `xnu/patches-ishtar/`), then
   the stock tree (`scripts/dtb2dts.py` on AOSPA's `dtbs/kalama-v2.dtb` + `dtbo.img` entry 06 into `ref/`).
4. For an iOS 27 kernel or ABI question, read sheng's `feat/ipados27-gpu-parity` branch (`../UniXNU-sheng`) and
   UniXNU's same-named branch; both are the reference implementation on this SoC.

## Rules

- The first machine (jf60678) has no `dtc`, `gh` or `ipsw` and installing tools is not allowed there: use stdlib
  Python, `~/miniconda3/bin/python3` (3.13) for UniXNU, `/usr/bin/python3` for HTTPS, macOS `compression_tool` and
  `aea`. Build and boot steps run on a machine with the tools listed in docs/HANDOFF.md.
- Keep upstream file names, boot-argument names (`sheng-*`), class names and bundle IDs when copying from sheng or
  UniXNU for now, and record the source commit of every copy. Renaming to ishtar is planned once the board boots
  (docs/HANDOFF.md, "Rename to ishtar").
- `board.kit` stays `sheng` until UniXNU's build scripts stop hard-coding `kits/sheng`.
- Any record holding original kernelcache addresses must be the iPhone17,2 one (kernelcache sha256
  `fa07057b...5f95`), never the iPad17,3 one (`38e6d9fa...780a`).
- Nothing is flashed except the userdata windows, and only on explicit request: they erase Android user data.
- Update the affected `porting.toml` areas (findings or evidence) with every change, and run:

```sh
cd ../UniXNU
~/miniconda3/bin/python3 ./unixnu status --json -D ../UniXNU-ishtar
~/miniconda3/bin/python3 scripts/porting-record.py check --device ../UniXNU-ishtar
~/miniconda3/bin/python3 ../UniXNU-ishtar/scripts/check-patch-series.py --xnu ../ref-src/xnu-12377
```

Report commands, revisions, outputs and device observations separately. Old-port results are evidence about the
hardware, not about this implementation.
