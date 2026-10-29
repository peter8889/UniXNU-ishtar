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
| ZAP firmware entry | `proprietary-files.txt` | T0 (needed at stage 3) |
| `Binaries/ishtar` (ishtar's stock UEFI modules and raw files) | uefi-ishtar `Binaries` submodule | T0 |
| Boot-image DTB `Resources/DTBs/ishtar.dtb` | `../uefi-ishtar` (not in git) | T0 |
| DRAM bank 1 entries (inferred, not measured on ishtar) | uefi-ishtar `ishtarPkg/Library/MemoryMapLib/MemoryMapLib.c` | T0, T9 |

## 2. Rules

- **Ask the user before** `fastboot flash userdata` (erases Android user data), before pushing anything, and before
  any other `fastboot flash`. `fastboot boot <img>` is the normal way to test: nothing persists.
- Never commit Apple, Qualcomm or Xiaomi binaries, keys or the unique chip ID (`.gitignore` covers the usual names).
  Exception by design: `Binaries/ishtar` lives in the user's own fork of Device-Binaries (T0); ask before making it public.
- Trusted sources only: UniXNU org repos, the submodules they pin (Project-Silicium, Microsoft Mu, OpenSSL), Apple
  OSS, AOSPA's ishtar kernel, the user's own repos and stock dump. Do not pull in other forks (e.g. wh1stl3/uefi-nuwa)
  or prebuilt blobs from elsewhere without asking.
- Names: everything this port owns carries ishtar names (patch files, board kit, audio ABI, UEFI package and
  drivers). Names shared with upstream components stay as they are; see "Rename to ishtar" in section 6.
- Every change updates the owning `porting.toml` area (findings or evidence); host/device evidence needs the full
  40-character commit. Old-port results are hardware facts, not evidence for this implementation.
- After editing the UniXNU or uefi-ishtar branch, re-export it into this repo (from this repo's root), then ask the
  user to push (section 8):
  `rm unixnu/*.patch && git -C ../UniXNU format-patch upstream/feat/ipados27-gpu-parity..ishtar/ios27 -o "$PWD/unixnu"`
  `rm firmware/*.patch && git -C ../uefi-ishtar format-patch 20ac23d5..ishtar -o "$PWD/firmware"`

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
# 1. This repository: the user's GitHub (or a bundle: git clone ishtar-ios27.bundle UniXNU-ishtar)
git clone https://github.com/markakash/UniXnu-ishtar UniXNU-ishtar
# 2. UniXNU with this port's commits (iOS 27 profile, kits/<board.kit>): the user's fork, branch ishtar/ios27
#    (or: clone UniXNU/UniXNU, switch -c ishtar/ios27 origin/feat/ipados27-gpu-parity, git am ../UniXNU-ishtar/unixnu/*.patch)
git clone -b ishtar/ios27 https://github.com/markakash/UniXNU UniXNU
git -C UniXNU remote add upstream https://github.com/UniXNU/UniXNU && git -C UniXNU fetch upstream
# 3. References
git clone https://github.com/UniXNU/UniXNU-sm8550-common                                   # 23b2049
git clone -b feat/ipados27-gpu-parity https://github.com/UniXNU/UniXNU-sheng               # 6ed0ba4 copied from
git clone https://github.com/markakash/UniXNU-ishtar-old ishtar                                # old iOS 18 port, 79ddf457
git clone --depth 1 -b vauxite https://github.com/AOSPA/android_device_xiaomi_ishtar-kernel # stock dtbs/
git clone --filter=blob:none https://github.com/apple-oss-distributions/xnu ref-src/xnu-12377 \
  && git -C ref-src/xnu-12377 checkout ac9718fb1af618d5ce8678d0dc6e8a58f252216f
# 4. Firmware: UniXNU's uefi-sheng + this port's ishtarPkg commit, branch ishtar (the user's fork once pushed;
#    until then: clone UniXNU/uefi-sheng, switch -c ishtar 20ac23d5, git am ../UniXNU-ishtar/firmware/*.patch)
git clone -b ishtar <user's uefi-ishtar fork> uefi-ishtar
git -C uefi-ishtar submodule update --init --recursive    # Binaries gains ishtar/ in T0
```

The repository names are the ones the user pushes to (section 8); if a clone fails, ask. If the UniXNU commits
conflict after an upstream move, rebase them onto `87bf1f9` and record the base you used.

Check the host side reproduces:

```sh
cd $W/UniXNU
./unixnu defconfig ishtar_ios27_defconfig -D ../UniXNU-ishtar
./unixnu fetch -D ../UniXNU-ishtar            # reuses the committed unixnu.lock pins (--update moves them)
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
dtb = "../uefi-ishtar/Resources/DTBs/ishtar.dtb"   # not in git: see T0
unique_chip_id = "<16 hex digits, nonzero, chosen once and kept>"
trust_cache = "<T6 output>"
data_ramdisk = "<T7 output>"
```

## 5. Tasks to the first boot

Run in order; each lists what to record. "Record" means: update the named `porting.toml` area and commit.

### T0. Stock HyperOS inputs (on the user's PC that has the stock dump)

The user has a dump of ishtar's stock HyperOS. Nothing below is downloaded from third parties.

1. **Find the images.** A fastboot ROM has `images/uefi.elf`, `xbl_s.melf`, `xbl_config.elf`, `vendor_boot.img`,
   `dtbo.img`; a partition dump has `uefi_a`, `xbl_a`, `xbl_config_a`, `vendor_boot_a`, `dtbo_a`, `modem_a` and the
   `odm`/`vendor` images. Record the HyperOS version (old port: `OS3.0.308.0.WMACNXM`) and the UEFI build string
   (expected `BOOT.MXF.2.1.1-00218-KAILUA-1.36233.1`).
2. **Extract the UEFI.** Build gus33000's UEFIReader (`git clone https://github.com/gus33000/UEFIReader`,
   `dotnet build -c Release`; it is the tool Device-Binaries sets are made with) and run it on the uefi image,
   exactly as the old port did (`ishtar/scripts/extract-stock.sh`, which also splits the vendor_boot DTBs):
   `dotnet UEFIReader.dll uefi.elf out/uefi`. Lay the result out as `Binaries/ishtar/` in Device-Binaries'
   format (compare `Binaries/nuwa/`, the same Kailua build): `QcomPkg/Drivers/<Name>/<Name>.inf|.efi|.depex`,
   `MdeModulePkg/...`, `RawFiles/` (`uefiplat.cfg`, `SecParti.cfg`, `uefipil.cfg`, `Panel_*.xml`, ...).
   Every path ishtarPkg uses must exist:
   `grep -rhoE 'Binaries/ishtar/[^ }]+' Platforms/Xiaomi/ishtarPkg | sort -u | while read f; do [ -e "$f" ] || echo MISSING $f; done`
   Copy the FFS GUID and UI name of `Panel_M1_42_02_0a_ltpo_dsc_cmd.xml` into `ishtarPkg/Include/RAW.inc`
   (the current GUID there is sheng's placeholder; it only matters with `USE_CUSTOM_DISPLAY_DRIVER = 1`).
3. **Host the set.** Fork `Project-Silicium/Device-Binaries` under the user's account (private is fine; ask before
   making it public), add `ishtar/` with a README (source ROM, versions, sha256 of the uefi image), push. In
   uefi-ishtar point `.gitmodules` `Binaries` at the fork, bump the submodule to that commit, commit on `ishtar`,
   re-export `firmware/`.
4. **Check the platform config.** Diff the extracted `RawFiles/uefiplat.cfg` against
   `ishtarPkg/Library/ConfigurationMapLib/ConfigurationMapLib.c` (sheng's values: single core, display thread off)
   and its memory map section against `MemoryMapLib.c`. Keep sheng's run-time choices unless ishtar's values are
   required; record every difference in the `firmware` area.
5. **Firmware files for later stages** (record path and sha256 in `proprietary-files.txt`, files under
   `.cache/firmware/`): GPU ZAP `odm: /firmware/a740_zap.mbn` (+ `.b00`-`.b02`; the `vendor` split copy is refused
   by TZ), ADSP `adsp.mdt`/`adsp.b*` and `adsp_dtb.mdt`/`adsp_dtb.b*` from the `modem` partition's FAT `/image`.
6. **From the phone** (Android, Magisk root):
   `adb shell su -c 'cat /sys/firmware/fdt' > ../uefi-ishtar/Resources/DTBs/ishtar.dtb` (boot-image DTB, not in git)
   and `adb shell su -c 'cat /proc/iomem' | grep "System RAM"` (needed by T9).

Record: area `firmware` (versions, hashes, fork URL and commit, config differences).

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

`uefi-ishtar` is UniXNU's own `uefi-sheng` (Mu-Silicium, commit `20ac23d`) plus one commit that adds
`Platforms/Xiaomi/ishtarPkg` and `Resources/Configs/ishtar.toml` ([firmware/](../firmware/)). The old
uefi-nuwa-based tree is not used. What ishtarPkg already does:

- Same UniXNU integration as sheng: `UniXNU`, `UniXNUDxe`, `DarwinBoot`, `UniXNURamDiskDxe`, DiskIo, FAT.
- `ISHTAR_VENDOR_HW = 0`: Mu drivers only; `SimpleFbDxe` keeps the panel the stock XBL lit (1440x3200, 60 Hz).
  The only vendor file built in is `Binaries/ishtar/RawFiles/SecParti.cfg` (T0).
- Own board drivers (copies of sheng's with new FILE_GUIDs): `IshtarKeyInputDxe` (same PMK8550/PM8550 key
  wiring as sheng), `IshtarBootMemoryDxe`, `IshtarGopLogDxe`, `IshtarDisplayDepexDxe`. The key driver's host test
  (`Drivers/IshtarKeyInputDxe/Test/keys_host.c`) has not been run. It is optional: run it only on a machine where
  the user allows running locally built binaries, and ask first.
- Memory map: sheng's reservations (identical on ishtar); DRAM bank 1 low `0x880000000 + 0x39D00000`, bank 1
  high `0x8C0000000 + 5 GiB`.
- Boot image: `Resources/Configs/ishtar.toml` from nuwa (header v1, FD at `0xA7100000`).

What this task still has to do:

1. Check the DRAM entries against the T0 `/proc/iomem` output before trusting them. Bank 1 low must stay inside a
   System RAM run (nuwa's 12 GB map has a 2 MiB hole at `0x8B9D00000`); bank 1 high can grow to the measured end
   (old port: `0x8C0000000-0xAFFFFEFFF`).
2. Build and boot:

```sh
./unixnu build package -D ../UniXNU-ishtar
./unixnu build firmware -D ../UniXNU-ishtar --uefi ../uefi-ishtar
./unixnu bootimg -D ../UniXNU-ishtar --uefi ../uefi-ishtar --dtb ../uefi-ishtar/Resources/DTBs/ishtar.dtb --ramdisk none
fastboot boot out/ishtar/ios-27.0.1-24A446/ishtar_ios27/boot/boot.img   # expect the UniXNU menu; nothing persists
```

3. Commit any uefi-ishtar change on its `ishtar` branch and re-export it into this repo
   (`rm firmware/*.patch && git -C ../uefi-ishtar format-patch 20ac23d5..ishtar -o "$PWD/firmware"`).

If the screen stays black after ABL: check the framebuffer PCDs in `ishtar.dsc` (1440x3200, 32 bpp) and that the
DTB keeps `/reserved-memory/splash_region` (board.toml adds it). If EDK II BaseTools fail on Apple Silicon, the old
port's `ishtar/scripts/build-uefi.py` shows flags that worked. Vendor drivers (`ISHTAR_VENDOR_HW = 1`) are a later
experiment: on sheng they blank the panel. Record: area `firmware` (commits, FD path, DTB source, memory map).

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
| 4 120 Hz | ishtar's panel is DSI command mode and the stock XBL leaves it at 60 Hz (panel XML `DSIRefreshRate 0x3C0000`): send the `wqhd_120hz` timing-switch DCS sequence from `ref/dtbo-06.dts` (panel "xiaomi 42 02 0a"), measure the TE interval, then boot with `sheng-vsync=120`. | `scripts/dtb2dts.py` on AOSPA `dtbs/dtbo.img --entry 6` |
| later | battery (old 2035 vs sheng's ADSP loader), cpufreq (2029/2033), USB Ethernet (2012), Wi-Fi (Ath12kWifi), 8 GiB window | [docs/MIGRATION.md](MIGRATION.md) |

To re-port records after an upstream change to sheng's or UniXNU's iPad records:
`scripts/ios-identity.py --product iPad17,3 --out out/ios-identity-ipad17,3`, then
`scripts/kc-port.py <iPad kc> <iPhone kc> --record <record> --out abi/<name>-d94ap.json` (must report 0 failed).

### Rename to ishtar

Done (everything this port owns): patch files `zzye-ishtar-cpu-idle`, `zzyf-ishtar-amp`,
`zzyd-ishtar-audio-addon-mount`, `zzzz-ishtar-ios27-bringup`, `soc/ishtar-platform-power`; `board.kit = "ishtar"`
(UniXNU `ishtar/ios27` commit "build: read the board package from kits/<board.kit>"); the audio ABI
(`package/IshtarAudioAbi.h`, `IshtarAudio*`, `ishtar_audio_*`, `IshtarAudio.driver`); the UEFI package
(`ishtarPkg`, `ISHTAR_VENDOR_HW`, `Ishtar*Dxe` drivers, `Binaries/ishtar`).

Kept on purpose: names that form an interface with code this port does not own. Renaming one side alone breaks it.

| Names | Read or defined by | To rename |
| --- | --- | --- |
| Boot arguments `sheng-log`, `sheng-data-reset`, `sheng-os*`, `sheng-exc*`, `sheng-autoreset`, `sheng-setup`, `sheng-lite`, `sheng-disable-*` and more (`grep -rhoE '"sheng-[a-z0-9_-]+' patches package`); `sheng-vsync` | ShengUfs, GopFramebuffer, the bring-up patch and the copied package | add ishtar-* aliases in those components (upstream option), then switch |
| Kernel symbols `sheng_idle_*`, `sheng_exc_*`, `sheng_sigp_*`, `sheng_prof_*`, `sheng_boot_*` and more (`grep -rhoE '\bsheng_[a-z]+_' patches package`) | defined by the bring-up and cpu-idle patches, read by the copied package and possibly by components | rename in patches and package together after a build proves no component references them |
| `XNU_SHENG_PMGR`, `sheng_pmgr_run` | sm8550-common's platform-power patch, re-patched by UniXNU's `zzz-boot-progress.patch` | upstream change in UniXNU and sm8550-common |
| Component IDs `ShengUfs`, `ShengHidInput`, class names `ShengBattery`, `ShengQrtr` | UniXNU catalog, sheng's package | upstream (catalog IDs are shared) |
| `scripts/build-sheng-*.py`, `build/sheng-*` output directories | UniXNU build scripts | upstream |

Do the kernel-symbol row once the kernel builds (a missed reference shows up as a link error); re-run
`check-patch-series.py` and keep it at 75/75.

## 7. Report back

For each task: command, full commit of this repo and of `UniXNU` `ishtar/ios27`, output path and sha256, result, and
what was seen on the phone. Missing inputs and decisions for the user (key handling, flashing) go first.

## 8. Repositories the user pushes

The user pushes; agents commit locally and say what to push.

| Local | Remote | Branch |
| --- | --- | --- |
| `UniXNU-ishtar` | `markakash/UniXnu-ishtar` | `main` |
| `UniXNU` | `markakash/UniXNU` (fork of `UniXNU/UniXNU`) | `ishtar/ios27` |
| `uefi-ishtar` | the user's fork of `UniXNU/uefi-sheng` | `ishtar` |
| `Binaries` (uefi-ishtar submodule) | the user's fork of `Project-Silicium/Device-Binaries`, private | default branch, with `ishtar/` (T0) |

Not pushed: `out/`, `ref/`, `local.toml`, `unixnu.local.toml`, `.cache/firmware/`, keys, IPSW members.
