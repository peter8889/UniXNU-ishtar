# Migration from the iOS 18 port

The iOS 18 port ([markakash/UniXNU-ishtar](https://github.com/markakash/UniXNU-ishtar) `79ddf457`, local `../ishtar`)
patched Bergamota's xnu-11215 tree (`Ishtar*` classes, iPhone XR identity, 16 KiB pages). This repository builds
UniXNU's arm64e xnu-12377 kernel with 4 KiB pages, so none of those patches apply as-is. Each one is either covered
by UniXNU/sheng code, ported as a board component, or dropped.

| Old patch | Function | New home | State |
| --- | --- | --- | --- |
| 2000 gicr-stride-from-adt | GICR stride 0x40000 | `sm8550.dtsi` `redistributor-stride` + ArmCpu | covered |
| 2001 no-physical-timer-write | Gunyah blocks CNTP writes | ArmCpu (sheng boots under the same hypervisor) | check at stage 0 |
| 2002 ufs-power-no-battery | SM8550 UFS GCC clocks | ShengUfs `GccUfs.h` | covered |
| 2003 early-fb-sm8550 | console at 0xb8000000 | DarwinBoot GOP handoff + GopFramebuffer | covered |
| 2004 alive-heartbeat | timer heartbeat line | `zzz-boot-progress.patch`, `package/BootLog.c` | replaced |
| 2005 gic-quiet-boot-interrupts | disable SPIs ABL/UEFI left pending | ArmCpu | check at stage 0; port if interrupts storm |
| 2006 (parked) raw-pixel diagnostics | | | dropped |
| 2007 ufs-root-error-visible | delay before root panic | ShengUfs diagnostics, boot log | dropped |
| 2008 ufs-wlun-active | START STOP UNIT to W-LUN 0xD0 | ShengUfs `NativeUfs.cpp` (same command) | covered |
| 2009 fb-keep-display-on | keep OLED on (no WLED) | display stage (GopFramebuffer power hooks) | port in stage 1 |
| 2010 keys-sm8550 | PMK8550 PON + PM8550 GPIO6 over SPMI v7 | board package button source | port in stage 2 |
| 2011-2019 touch | FTM5 over GENI SE8 with GPI DMA, PM8008, RPMh votes, THP off | board package touch component + IOHIDDevice (ShengHidInput model) | port in stage 2 |
| 2020 a740-gpu | Adreno 740 | UniXNU Adreno740 + AdrenoMetal + Sm8550Platform | replaced (old path lagged) |
| 2021 push | plugin push over USB | UniXNU GPU addon / payload | dropped |
| 2022 fb-scaler-rows | CPU canvas scaler | DPU VIG scaler (display stage) | replaced |
| 2023 vfs-attrlist-ios18 | iOS 18 attribute bits | xnu-12377 + Darwin 26 patches | dropped |
| 2024 ufs-ready-retries | UFS ready polling | ShengUfs | check at stage 0 |
| 2025 dpu-sm8550-flip | DPU double-buffer flip, tear check | display stage; compare sheng `ShengDpuObservation.c`, `sheng-dpu-scanout` | port in stage 4 (120 Hz) |
| 2026 reboot-sm8550 | reset | `package/BootReset.c` (PSCI SYSTEM_RESET/RESET2, SPMI) | replaced |
| 2027 surface-use-counts | old GPU path | | dropped |
| 2028 gpu-maint-knob | old GPU path | | dropped |
| 2029, 2033 cpufreq | EPSS governor + downshift fix | power area; compare sheng `CpuFreqProbe.cpp` | port later |
| 2030 usb-drop-evidence | USB diagnostics | network area (USB Ethernet) | port later |
| 2031 amp-clusters | E/P clusters | `zzyf-sheng-amp.patch` + DTS `unixnu,cluster-type` | covered |
| 2032 thread-names | debug names | | dropped |
| 2034 fbcon-once | console registration fix | | dropped |
| 2035 adsp-battery | ADSP takeover, GLINK/QRTR battmgr | sheng `AdspFirmware.c`, `QcomGlink.c`, `QcomQrtr.c`, `ShengBattmgr.c` | port later; sheng loads ADSP from XNU |
| `uefi/darwinboot-32mb-block.patch` | 32 MiB kernel placement for 16 KiB pages | not needed with 4 KiB pages | dropped |
| `gpu/adrenometal-0001-ios18.patch` | iOS 18 Metal plugin ABI | UniXNU AdrenoMetal | dropped |

## iPhone17,2 records

Same build as the iPad profile, so class layouts, vtable slot numbers and PAC diversities match; only addresses
move. `scripts/kc-port.py` ported all of them with 0 failures ([report](../reports/kc-port-24A446-d94ap.txt)).

| Record | iPad17,3 source | iPhone17,2 record | Used by | Stage |
| --- | --- | --- | --- | --- |
| `early_security_init` | iPad profile | `0xfffffff00921000c` in the ios profile | prelink | 0 |
| `[root]` volume UUIDs and digests | iPad profile | REQUIRED (needs AEA decryption) | payload, root policies | 0 |
| `legacy-display-24A446.json` | `UniXNU-sheng/scripts/` | `abi/legacy-display-24A446-d94ap.json` | `build-gop-legacy-display-27.py` | 1 |
| `hid-device-24A446.json` | `UniXNU-sheng/scripts/` | `abi/hid-device-24A446-d94ap.json` | HID input archive | 2 |
| `abi/original-classes.json` | iPad profile | ios profile `abi/original-classes.json` | UniXNU check scripts | 1-2 |
| `ioaccelerator-base-abi-24A446.json` | `UniXNU/scripts/data/` | `abi/ioaccelerator-base-abi-24A446-d94ap.json` | `build-adreno740-accelerator.py` | 3 |
