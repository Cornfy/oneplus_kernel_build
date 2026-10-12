# OnePlus 12 自定义内核构建

本项目 fork 自 [WildKernels/OnePlus_KernelSU_SUSFS](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS)，用于通过 GitHub Actions 构建个人使用的 OnePlus 12 内核。目前仅保留 Android 16 系统对应的设备配置，关闭 SUSFS，保留现有构建流程和其他所需特性，并在构建时集成 KernelSU Next。

已在本人的 CPH2581、`CPH2581_16.0.1.300(EX01)` 系统上验证 KSUN 33342 构建能够启动。该记录不代表其他机型、地区或系统版本的兼容性。

## 配置

设备配置位于 [configs/a16/OP12-6.1.118.json](configs/a16/OP12-6.1.118.json)，源码和预编译依赖由 [manifest](manifests/a16/oneplus_12_6.1.118_w.xml) 指定。

| 项目 | 当前设置 |
|---|---|
| 设备 / SoC | OnePlus 12 / SM8650（pineapple） |
| 系统版本 | A16 |
| 内核基线 | Android 14 / Linux 6.1.118 |
| KernelSU | 默认 KernelSU Next `dev`，每次构建先解析提交 |
| SUSFS | 关闭 |
| 编译优化 / LTO | 默认 O2 / thin |
| Rust / HMBIRD | 关闭 |

设备 JSON 中启用了优化补丁、DroidSpace 支持、BBG、BBR / BBR3、TTL、IP Set、Unicode 补丁和 NTSync 等选项。具体配置与实际应用情况以设备 JSON、构建日志为准。A16 是系统配置标签，`android14` 是内核基线，两者并不矛盾。

部分依赖会在构建时获取；同一仓库提交重复构建也可能因 KernelSU Next 或其他浮动依赖更新而得到不同结果。

## 构建与发布

打开 Actions → **Build and Release OnePlus Kernels** → **Run workflow**：

- `op_model` 选择 `A16`。
- `ksu_options` 默认 `[{"type":"ksun","hash":"dev"}]`；也可填写已验证提交以固定 KernelSU Next。
- `optimize_level` 保持默认 `O2`，其余编译选项按需调整。
- `make_release` 默认开启；构建成功后公开发布已有 AnyKernel3 ZIP。

发布不依赖 SUSFS 版本，标签为 `op12-a16-<run_id>-<run_attempt>`。Release 包含构建链接、构建项目提交、KernelSU 解析提交及 ZIP SHA256。关闭发布时仍可从该次 Actions 获取构建产物。

[Releases](https://github.com/Cornfy/oneplus_kernel_build/releases) · [Actions](https://github.com/Cornfy/oneplus_kernel_build/actions)

## 刷写前准备

先保存同版本官方 ROM 提取的镜像及启动分区备份，并实际验证另一槽可以进入 Recovery → fastbootd。另一槽无需启动 Android，但仅有 boot/init_boot 镜像或安装了 TWRP，并不等于救援入口可用。

本机实测切槽后需要：**完全关机 → 按键进入 Bootloader → `fastboot reboot fastboot`**。在 fastbootd 用 `fastboot getvar is-userspace` 确认返回 `yes`。

仅向当前使用槽安装新内核，保留已验证备用槽。可使用支持 AK3 的刷写应用、兼容 Recovery，或本机已确认支持 AK3 的 KernelSU Next 管理器。fastbootd 用于刷分区镜像，不能直接刷 AK3 ZIP。

- [备用槽准备及恢复流程](docs/OP12_Rescue_Preparation.md)
- [构建与救砖实测记录](docs/OnePlus12_Kernel_Build_And_Rescue_Notes.md)

## USB 切槽辅助脚本

[scripts/switch_slot.py](scripts/switch_slot.py) 在普通客户端切槽失败时，按 Fastboot USB 接口标识 `ff/42/03` 和双向 Bulk 端点识别设备，再发送 `set_active:a/b`。它不刷分区、不自动重启，也不能绕过手机端限制。

需要 Python、PyUSB 和可用的 libusb 后端。Arch Linux 可安装 `python-pyusb`、`libusb`；可选的自动查询还需要 PATH 中的 `fastboot`。

```bash
# 交互模式：先询问是否查询；跳过查询时手动输入当前槽
doas python3 scripts/switch_slot.py

# 已知当前是 A：不查询，提示并确认切到 B
doas python3 scripts/switch_slot.py --current-slot a

# 已知当前是 B：不查询，提示并确认切到 A
doas python3 scripts/switch_slot.py --current-slot b

# 不知道当前槽，但已明确救援目标：指定目标，不查询
doas python3 scripts/switch_slot.py --slot b
```

所有路径均需输入 `yes` 才发送切槽命令，没有默认目标 B。不确定当前槽或救援目标时取消操作。

本机曾在新版脚本执行期间出现 `Press any key to shutdown`，而原始无查询命令有效；新增 fastboot 查询可能相关，根因尚未证实。查询失败或超时不会阻止后续选择，但若手机已经异常，需重新进入可操作的 Bootloader，再使用跳过查询模式。收到 `OKAY` 仅表示指令被接受，不证明目标槽能够启动。

## 本地文件

`op12_flash/` 和 `rescue-backup/` 是本地固件及备份目录，已忽略，不纳入仓库。Python 字节码缓存也已忽略。本文中的历史校验值仅用于对应文件，不能代替核对自己的机型、版本与镜像来源。

本项目依赖上游构建脚本、OnePlus 开源源码、WildKernels 补丁及工具、KernelSU Next 和 AnyKernel3 等项目；使用各组件时遵循其原有许可。

USB VID/PID 不硬编码；`18d1:d00d` 仅是本机曾观察到的值。脚本先列出检测到的接口，仅接受唯一 Fastboot 接口；多台时请拔掉其他设备。reset 后按 USB 物理端口重新识别，避免地址改变时选错设备。枚举描述符不发送 Fastboot getvar，但仍涉及 USB 通信，不保证异常 Bootloader 不受影响。
