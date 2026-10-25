<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img alt="UniXNU" src="assets/logo-light.svg" width="200">
  </picture>
</p>

<p align="center">
  <a href="https://t.me/petegroup"><img alt="Telegram" src="assets/telegram.svg"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

# UniXNU ishtar

小米 13 Ultra（代号 `ishtar`）的设备支持，SoC 为高通 SM8550。设备配置选择
[UniXNU-sm8550-common](https://github.com/UniXNU/UniXNU-sm8550-common) 与 UniXNU 中的
`ipados-17.7.11-21H461` OS profile。本板复用 `sheng` 的 kit，因此 archive 方案、
ADT 生成器和打包脚本与 SM8550 参考板共享。

## 状态

内核、载荷和启动镜像均已构建通过，组装后的镜像也通过自身的往返校验。尚未在
ishtar 真机上加载任何内容。

| 部分 | 状态 |
| --- | --- |
| 配置、固件、CPU、内存、镜像组装、诊断 | 已实现 |
| 存储、显示、输入、GPU、网络、音频、电源 | 未开始 |

存储和显示在设备树中有描述，但被编译关闭。GPU 链接到桩实现。触控固件已固定
版本，但驱动未被选中。各条目的输入、发现和完成标准见
[porting.toml](porting.toml)。

## 结构

| 路径 | 内容 |
| --- | --- |
| `porting.toml` | 各子系统的输入、发现、证据和完成标准 |
| `board.toml` | 设备配置与组件选择 |
| `feeds.toml` | 固定的 SoC 源码 |
| `configs/gpu_defconfig` | 板级内核设置 |
| `configs/bringup_defconfig` | 关闭全部可选组件，用于早期入口调试 |
| `dts/ishtar.dts` | 内存、保留区与外设启用 |
| `patches/xnu/series` | 板级补丁 |
| `proprietary-files.txt` | 固件输入路径 |
| `package/` | 设备策略与诊断 |
| `drivers/MiniDisplay/` | 帧缓冲与 surface 实现，未接入构建 |
| `scripts/` | 设备构建与检查工具 |

`configs/sheng_defconfig` 继承自参考板，保留作为对照点。本板使用
`gpu_defconfig` 构建，`board.toml` 中指定了它。

`Adreno740` 与 `Sm8550Platform`、`AdrenoPM4`、`AdrenoFirmware`、`ArmSmmu4K`
一同被选中，但内核链接使用 `build/adreno-link-stubs/libAdrenoLinkStubs.a`。
完整驱动需要载荷阶段的加速器 ABI，而内核链接没有对应的 archive 变量，因此由
`scripts/build-adreno-link-stubs.py` 提供桩实现。

`ShengUfs`、`VirtioMmioBlock` 和 `VerifiedRoot` 已被选中，但
`CONFIG_XNU_NATIVE_UFS` 保持关闭。这样硬件描述是完整的，启用存储只需改配置，
而不必改设备树。显示同理：`dts/ishtar.dts` 启用了 `ufs`、`ufsphy`、`gpu`、
`gmu` 和 `gpu_smmu`，而 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` 与
`CONFIG_XNU_NATIVE_MOBILE_DISPLAY` 仍为关闭。

无驱动时唯一可用的显示输出是 `board.toml` 中的直接帧缓冲路径：位于
`0xb8000000` 的 `panic_framebuffer`，1440x3200，行跨度 5760 字节。崩溃界面和
启动进度都通过它输出。

`drivers/MiniDisplay/` 中的帧缓冲与 surface 实现尚无 archive 构建。它没有
archive 条目、没有 `bsd_init` 挂钩、也没有配置开关，因此在补齐之前不生效。

## 开发记录

每次子系统改动都要维护 [porting.toml](porting.toml)。它记录硬件、配置、操作
步骤、发现、证据和完成标准。维护者和 agent 遵循[记录指南](https://unixnu.com/zh/porting/records)。
`Porting record` CI 检查会校验结构、组件覆盖情况，以及代码改动是否同步更新了
发现或证据。

共享组件来自所选 profile 和 UniXNU 组件目录。修改存储资源或策略前请先阅读
[UFS 指南](https://unixnu.com/zh/porting/ufs)。

## 构建

固件必须嵌入 UniXNU、UniXNUDxe、DarwinBoot 和共享的 `UniXNURamDiskDxe`，并
支持 DiskIoDxe 与 FAT。这些模块提供载荷配置及其启动项。板级包位于 sheng 固件
树中的 `Platforms/Xiaomi/ishtarPkg`。参见
[固件集成](https://unixnu.com/zh/porting/uefi-firmware#required-integration)。

在 UniXNU 检出目录中执行以下命令：

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

输出位于 `out/ishtar/ipados-17.7.11-21H461/gpu/`。载荷步骤编译硬件 DTS 并写出
`kernel.macho.adt`。启动镜像通过 `--dtb` 取用固件的 FDT。

构建输入包括所选 kernelcache、固件 DTB、厂商固件和 UEFI 源码。二进制输入保存在
本地缓存。`proprietary-files.txt` 按上游提交记录固件清单。

内核构建有一个已知偶发问题：clang 前端偶尔在 `osfmk/vm/vm_kern.c` 上崩溃，并
写出被截断的 `.o.json`。重跑该单个编译单元即可恢复。重放时必须保留 `-MJ`，并
且必须带上 `-DXNU_BOOT_PROGRESS=1`，否则控制台钩子会静默编译为空操作。

## 文档

文档站维护在 UniXNU 中：

- [设备页面](https://unixnu.com/zh/devices/ishtar)
- [构建与启动](https://unixnu.com/zh/building)
- [设备仓库规范](https://unixnu.com/zh/porting/device-repository)
- [设备树规范](https://unixnu.com/zh/porting/device-tree)
- [组件目录](https://unixnu.com/zh/reference/components)
- [迁移](https://unixnu.com/zh/porting/migration)

构建结果与真机的启动、存储、显示、输入和 GPU 观察请分开报告，并附源码版本和
命令。

## 联系

移植讨论在 Telegram 群 [@petegroup](https://t.me/petegroup)。构建结果、启动
检查点和硬件观察仍应写入 `porting.toml` 和 issue 追踪器，因为群组是对话渠道，
不是记录。

## 本地构建输入

把设备路径和启动参数保存在 UniXNU 检出目录的 `unixnu.local.toml`。参见
[配置参考](https://unixnu.com/zh/reference/configuration#local-build-inputs)。
参数改动需要重新构建载荷和启动镜像。参见
[启动参数](https://unixnu.com/zh/xnu/boot-arguments#apply-arguments)和
[绿色交接条诊断](https://unixnu.com/zh/guide/debugging#green-bar)。
