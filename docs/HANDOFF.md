# Handoff: first iOS 27 boot on ishtar

For an agent on a machine that has the build tools this repository's first machine lacked. Read
[AGENTS.md](../AGENTS.md), [README.md](../README.md) and [porting.toml](../porting.toml) first; this file is the
ordered task list that takes the board from "host-checked" to the first `fastboot boot`.

## 1. Where things stand (2026-10-29)

Goal: iOS 27.0.1 (24A446) on the Xiaomi 13 Ultra (`ishtar`, SM8550-AB), identity iPhone 16 Pro Max (`iPhone17,2`,
D94AP), built with UniXNU on xnu-12377.121.6, reusing sheng's iPadOS 27 work on the same SoC.

Done and checked on the host (no build, no boot yet):

| Item | Evidence |
| --- | --- |
| Board config, DTS, stage 0 defconfig, package | `./unixnu status` and `defconfig` resolve |
| Kernel patch order (64 arch + 2 SoC + 4 OS + 5 device) | 75/75 apply: [reports/patch-series-xnu-12377.txt](../reports/patch-series-xnu-12377.txt) |
| iOS 27 iPhone17,2 profile (UniXNU commits in [unixnu/](../unixnu/)) | IPSW, kernelcache sha256 `fa07057b…5f95`, D94AP identity, prelink roots |
| AMFI init address `0xfffffff00921000c` and the four ABI records | ported from iPad17,3 with 0 failures: [reports/kc-port-24A446-d94ap.txt](../reports/kc-port-24A446-d94ap.txt) |
| Porting record | `scripts/porting-record.py check` passes (14 areas) |

Open values (search for `REQUIRED` and `00000000-0000-0000-0000-000000000000`):

| Value | File | Task |
| --- | --- | --- |
| `[root]` os/systemos volume UUIDs and image sha256, `[payload.adt] root_match_volume_uuid` | UniXNU `profiles/os/ios-27.0.1-24A446/profile.toml` | T4 |
| `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` | `configs/ishtar_ios27_defconfig` | T7 |
| `[userdata] last_lba` (derived, may be short) | `board.toml` | T1 |
| ZAP firmware entry | `proprietary-files.txt` | stage 3, not needed for stage 0 |

## 2. Rules

- **Ask the user before** `fastboot flash userdata` (erases Android user data), before pushing anything, and before
  any other `fastboot flash`. `fastboot boot <img>` is the normal way to test: nothing persists.
- Never commit Apple, Qualcomm or Xiaomi binaries, keys or the unique chip ID (`.gitignore` covers the usual names).
- Keep sheng/UniXNU file names, boot-argument names (`sheng-*`) and symbols for now. Renaming to ishtar is planned
  but deferred to save time until the board boots; see "Rename to ishtar" in section 6.
- Every change updates the owning `porting.toml` area (findings or evidence); host/device evidence needs the full
  40-character commit. Old-port results are hardware facts, not evidence for this implementation.
- After editing the UniXNU branch, re-export its patches into this repo (from this repo's root):
  `rm unixnu/*.patch && git -C ../UniXNU format-patch origin/feat/ipados27-gpu-parity..ishtar/ios27 -o "$PWD/unixnu"`

## 3. Machine

macOS (Apple Silicon) with:

| Tool | Why |
| --- | --- |
| Xcode with the iphoneos SDK | kernel step (`xcodebuild`, Apple clang) |
| Python 3.11+ | UniXNU CLI (`tomllib`) |
| `brew install llvm dtc mtools cmake ninja unifdef` | firmware/boot image (lld), payload ADT (dtc), payload FAT (mtools), kernel refs |
| `brew install blacktop/tap/ipsw` | AEA key fetch for the OS and SystemOS images (`ipsw fw aea --key`) |
| Android platform tools (`adb`, `fastboot`) | geometry, boot |
| ~80 GB free | IPSW members (OS image ~10 GB decrypted), userdata image, XNU build |

macOS `/usr/bin/aea`, `hdiutil`, `diskutil` and `compression_tool` are used as-is. A Linux host can build the kernel
(`sudo scripts/linux/setup-toolchain.py` in UniXNU) but the Data seed, Skip Setup and AEA steps need macOS.

## 4. Get the sources

All repositories sit side by side in one directory (`$W` below).

```sh
W=~/src/ishtar-ios27 && mkdir -p $W && cd $W
# 1. This repository. It is not published yet: ask the user for the remote, or take a bundle from the first machine:
#    (first machine) git -C UniXNU-ishtar bundle create ishtar.bundle --all
git clone <remote-or-ishtar.bundle> UniXNU-ishtar
# 2. UniXNU at the upstream iPadOS 27 branch + this port's profile commits
git clone https://github.com/UniXNU/UniXNU && cd UniXNU
git switch -c ishtar/ios27 origin/feat/ipados27-gpu-parity    # was 87bf1f9 when the patches were made
git am ../UniXNU-ishtar/unixnu/*.patch && cd ..
# 3. References
git clone https://github.com/UniXNU/UniXNU-sm8550-common                                   # 23b2049
git clone -b feat/ipados27-gpu-parity https://github.com/UniXNU/UniXNU-sheng               # 6ed0ba4 copied from
git clone https://github.com/markakash/UniXNU-ishtar ishtar                                # old iOS 18 port, 79ddf457
git clone --depth 1 -b vauxite https://github.com/AOSPA/android_device_xiaomi_ishtar-kernel # stock dtbs/
git clone --filter=blob:none https://github.com/apple-oss-distributions/xnu ref-src/xnu-12377 \
  && git -C ref-src/xnu-12377 checkout ac9718fb1af618d5ce8678d0dc6e8a58f252216f
# 4. Firmware: ask the user where uefi-ishtar lives (Mu-Silicium fork of wh1stl3/uefi-nuwa with ishtarPkg).
git clone --recurse-submodules <uefi-ishtar remote> uefi-ishtar
```

If `git am` conflicts because upstream moved, apply onto `87bf1f9` instead and record the base you used.

Check the host side reproduces:

```sh
cd $W/UniXNU
./unixnu defconfig ishtar_ios27_defconfig -D ../UniXNU-ishtar
./unixnu fetch -D ../UniXNU-ishtar            # writes ../UniXNU-ishtar/unixnu.lock: commit it
./unixnu status --json -D ../UniXNU-ishtar     # arm64e, sm8550, ios-27.0.1-24A446, 75 patches, 16 components
python3 scripts/porting-record.py check --device ../UniXNU-ishtar
python3 ../UniXNU-ishtar/scripts/check-patch-series.py --xnu ../ref-src/xnu-12377   # 75/75
cp unixnu.example.toml unixnu.local.toml       # fill in as the tasks below produce inputs (ignored by git)
```

`unixnu.local.toml` for this board:

```toml
[build]
device = "../UniXNU-ishtar"
uefi = "../uefi-ishtar"
dtb = "../uefi-ishtar/Resources/DTBs/ishtar.dtb"   # the DTB the old port appended; see T9
unique_chip_id = "<16 hex digits, nonzero, chosen once and kept>"
trust_cache = "<T6 output>"
data_ramdisk = "<T7 output>"
```

## 5. Tasks to the first boot

Run in order; each lists what to record. "Record" means: update the named `porting.toml` area and commit.

### T1. Userdata geometry (phone in Android or fastboot)

```sh
adb shell cat /sys/block/sda/sda30/start /sys/block/sda/sda30/size   # 512-byte sectors; sda30 = userdata on LUN 0
fastboot getvar partition-size:userdata                             # bytes, cross-check
```

`first_lba = start / 8`, `last_lba = (start + size) / 8 - 1` (4096-byte blocks). Expected first_lba 3092544
(0x2f3040, old port). Write both to `board.toml [userdata]`. Record: area `storage`.

### T2. IPSW members

```sh
./unixnu ipsw info -D ../UniXNU-ishtar          # must show iPhone17,2 27.0.1 24A446, d94ap, 0x8140, board 14
./unixnu ipsw fetch -D ../UniXNU-ishtar         # KernelCache, DeviceTree, StaticTrustCache, Cryptex1,SystemTrustCache
./unixnu ipsw fetch OS Cryptex1,SystemOS -D ../UniXNU-ishtar
```

The IPSW is read with HTTP range requests (no full 12 GB download). Members land in `out/ipsw/24A446/`.
The decompressed kernelcache must hash to `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`.

### T3. Kernel (stage 0)

```sh
./unixnu build kernel -D ../UniXNU-ishtar
```

Output `out/ishtar/ios-27.0.1-24A446/ishtar_ios27/kernel/kernel.macho`. Read `logs/` for the prelink report:
`early_security_initializers` must name `com.apple.driver.AppleMobileFileIntegrity` at `0xfffffff00921000c`, and
the collection slide must be 0 (the iPhone fileset already sits at `0xfffffff007004000`). The `ShengUfs` archive
needs T4/T5 first (it reads `[root]` and `build/verified-root-24A446`); if those are missing, build once to get the
XNU compile records, then come back after T5. Record: area `packaging` (host evidence: command, commit, result).

Likely first failures and where to look:
- archive step refuses the profile: `scripts/build-sheng-source-storage.py` checks arm64e and iOS >= 26 only.
- unresolved original symbols at prelink: compare with sheng's iPadOS 27 prelink log; roots are in the profile.

### T4. Root image identity (fills the profile `[root]`)

```sh
python3 - <<'EOF'
import sys; sys.path.insert(0, 'scripts')
from unixnu.ipsw import decrypt_aea
from pathlib import Path
for name in ('043-69909-664.dmg.aea', '043-68526-711.dmg.aea'):   # OS, Cryptex1,SystemOS (from ipsw info)
    print(decrypt_aea(Path('out/ipsw/24A446') / name))
EOF
shasum -a 256 out/ipsw/24A446/043-69909-664.dmg out/ipsw/24A446/043-68526-711.dmg
hdiutil attach -nomount -readonly out/ipsw/24A446/043-69909-664.dmg   # then: diskutil apfs list
hdiutil attach -nomount -readonly out/ipsw/24A446/043-68526-711.dmg
```

Take the APFS **volume** UUID of each image (not the container UUID); detach afterwards. Fill
`profiles/os/ios-27.0.1-24A446/profile.toml` in UniXNU: `os_volume_uuid`, `os_image_sha256`, `systemos_volume_uuid`,
`systemos_image_sha256`, and `[payload.adt] root_match_volume_uuid = os_volume_uuid`. The digests are the sha256 of
the decrypted UDIF `.dmg` files (what `build-owner-os-policy.py` hashes and what `verification.json image_sha256`
must equal). Commit on `ishtar/ios27`, re-export to `unixnu/`.
Record: area `storage`.

### T5. Owner root policies (`build/verified-root-24A446/`)

`build-sheng-source-storage.py` needs, for `OS` and `SystemOS`: `manifest.bin`, `trusted-key.bin` (395 bytes, same
for both) and `verification.json` (`real_c_signature_and_block_verification: true`, `image_sha256`, `volume_uuid`,
`trusted_key_sha256`). UniXNU has no published producer for 24A446: `scripts/build-owner-os-policy.py` is the iPadOS
17 one (hard-coded image name and UUID, keys in `build/verified-root-host/keys/owner.pem`). Generalise it for the two
iPhone17,2 images (VerifiedRoot component, `kits/VerifiedRoot`), generate an owner key pair once and keep it out of
git. If this blocks, ask the user to ask the UniXNU maintainers (t.me/unixnu) for their 24A446 policy tool.
Record: area `storage`.

### T6. Trust cache bundle

`scripts/build-original-system-trust.py` bundles the two unchanged Apple trust-cache modules
(`StaticTrustCache`, `Cryptex1,SystemTrustCache` from T2). Check it against the iPhone17,2 members (it may pin the iPad
ones) and point `trust_cache` in `unixnu.local.toml` at the result. Record: area `packaging`.

### T7. Data seed and its volume UUID

The writable Data volume comes from a packed APFS seed (`.dbr`). Candidates: `scripts/prepare-owner-data-fixture.py`
(small seed from the OS image's initial var tree), then `scripts/seed-data-grow.py --auto` (sizes it from
`fastboot getvar partition-size:userdata`). Read the seed's APFS volume UUID and put it in
`configs/ishtar_ios27_defconfig` `CONFIG_XNU_OWNER_DATA_VOLUME_UUID`, then rebuild the kernel (T3).
Record: area `storage`.

### T8. Userdata image (do not flash yet)

```sh
./unixnu build userdata --dry-run -D ../UniXNU-ishtar
./unixnu build userdata -D ../UniXNU-ishtar
```

Check `userdata/userdata-root.json`: windows fit between `first_lba` and `last_lba`, the reserve at the end stays
free, hashes match T4.

### T9. Firmware

uefi-ishtar already shows the UniXNU menu and runs DarwinBoot (old port), but it must also embed
`UniXNURamDiskDxe`, `UniXNUDxe`, `DiskIoDxe` and FAT so the payload ramdisk is found. Reference change: uefi-sheng
commit `34c9880` ("use the shared UniXNU RAM disk driver") and
<https://unixnu.com/porting/uefi-firmware#required-integration>. Board settings are in `board.toml [firmware]`.

```sh
./unixnu build package -D ../UniXNU-ishtar
./unixnu build firmware -D ../UniXNU-ishtar --uefi ../uefi-ishtar
```

If EDK II BaseTools fail on Apple Silicon, the old port's `ishtar/scripts/build-uefi.py` builds uefi-ishtar
directly and shows the working flags. Known uefi-ishtar facts: `#ABL` in `uefipil.cfg [AUTO]`, DXE heap
0xBAE00000+0x0D1C0000, ADSP started by UEFI (`FULL_ADSP`). Record: area `firmware` (commit, FD path, memory map).

### T10. Payload and boot image

```sh
./unixnu build payload -D ../UniXNU-ishtar        # uses unixnu.local.toml inputs; needs dtc
./unixnu bootimg -D ../UniXNU-ishtar --uefi ../uefi-ishtar --dtb ../uefi-ishtar/Resources/DTBs/ishtar.dtb
```

Check `payload/payload.json` (kernel args, ADT sha) and `boot/boot.json` (`ramdisk_bytes` nonzero). The ADT must
show `model = iPhone17,2` and `/chosen/root-matching` with the T4 UUID.

### T11. Boot (with the user's go-ahead)

```sh
fastboot flash userdata out/ishtar/ios-27.0.1-24A446/ishtar_ios27/userdata/userdata-root.img   # ASK FIRST: erases Android data
fastboot boot out/ishtar/ios-27.0.1-24A446/ishtar_ios27/boot/boot.img
```

There is no UART: watch the panel (`-v` console) and film it. Expected order: UniXNU menu → DarwinBoot → XNU
console → 8 CPUs → UFS root mount → launchd. The UFS boot log (`sheng-log=1`) is at the end of userdata; read it
with sheng's `scripts/read-sheng-log.py`. Record: device evidence in `cpu`, `storage`, `diagnostics`, with the image
sha256 from `boot.json`.

## 6. After stage 0

| Stage | Work | Inputs already here |
| --- | --- | --- |
| 1 display | Copy sheng's `scripts/build-gop-legacy-display-27.py` into `scripts/`, place `abi/legacy-display-24A446-d94ap.json` beside it as `legacy-display-24A446.json`, add it to `[kernel] archives`, set `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`, copy sheng's `offline-legacy-*` kernel args. Then DPU scaling 1320x2868 → 1440x3200 (old patch 2025). | ported record; old `2025` patch |
| 2 touch, keys | Port old patches 2011-2019 (FTM5 over GENI SE8 with GPI DMA, PM8008 L7, RPMh votes, SIDs 0x436/0x423, THP off) and 2010 (keys) into `package/` against 12377; feed an IOHIDDevice like ShengHidInput. UniXNU QcomGeniSpi has no GPI path. | `abi/hid-device-24A446-d94ap.json`; `../ishtar/xnu/patches-ishtar/` |
| 3 GPU | Make UniXNU `scripts/build-adreno740-accelerator.py` pick `abi/ioaccelerator-base-abi-24A446-d94ap.json` by kernelcache sha256; add the Adreno archives and `CONFIG_XNU_NATIVE_ADRENO=y`; ZAP = stock `/odm/firmware/a740_zap.mbn`. | ported record |
| 4 120 Hz | ishtar's panel is DSI command mode: switch it to its `wqhd_120hz` timing (uefi-ishtar panel config, or the DCS sequence in `ref/dtbo-06.dts`, panel "xiaomi 42 02 0a"), measure the TE interval, then boot with `sheng-vsync=120`. | `scripts/dtb2dts.py` on AOSPA `dtbs/dtbo.img --entry 6` |
| later | battery (old 2035 vs sheng's ADSP loader), cpufreq (2029/2033), USB Ethernet (2012), Wi-Fi (Ath12kWifi), 8 GiB window | [docs/MIGRATION.md](MIGRATION.md) |

To re-port records after an upstream change to sheng's or UniXNU's iPad records:
`scripts/ios-identity.py --product iPad17,3 --out out/ios-identity-ipad17,3`, then
`scripts/kc-port.py <iPad kc> <iPhone kc> --record <record> --out abi/<name>-d94ap.json` (must report 0 failed).

### Rename to ishtar (planned, after the board boots)

The user wants no `sheng` in this repository's names. Deferred only to save time. In order of cost:

1. File names (safe, local): `git mv` `zzye-sheng-cpu-idle` -> `zzye-ishtar-cpu-idle`, `zzyf-sheng-amp` ->
   `zzyf-ishtar-amp`, `zzyd-sheng-audio-addon-mount` -> `zzyd-ishtar-audio-addon-mount`,
   `zzzz-sheng-ipados27-bringup` -> `zzzz-ishtar-ios27-bringup`, `soc/sheng-platform-power` ->
   `soc/ishtar-platform-power`, `package/ShengAudioAbi.h` (and its include in `BootLog.c`). Update both `series`
   files (keep the upstream name as a comment for diffs), `porting.toml`, `docs/MIGRATION.md`, then rerun
   `check-patch-series.py` (must stay 75/75) and refresh `reports/`.
2. Boot arguments `sheng-*` (`sheng-log`, `sheng-data-reset`, `sheng-vsync`, ...): read by the copied package,
   the bring-up patch and the ShengUfs/GopFramebuffer components, so renaming them means patching those
   components too (local forks or upstream options).
3. Identifiers fixed by UniXNU: `XNU_SHENG_PMGR` / `sheng_pmgr_run` (patched again by UniXNU's
   `zzz-boot-progress.patch`), `board.kit = "sheng"` (UniXNU scripts hard-code `kits/sheng`), component IDs
   `ShengUfs`, `ShengHidInput`. These need UniXNU changes first (e.g. scripts taking `board.kit`).

## 7. Report back

For each task: command, full commit of this repo and of `UniXNU` `ishtar/ios27`, output path and sha256, result, and
what was seen on the phone. Missing inputs and decisions for the user (key handling, flashing) go first.
