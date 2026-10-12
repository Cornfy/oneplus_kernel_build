# OnePlus 12 备用槽与离线救援准备

适用于本仓库记录的 CPH2581。本文是准备流程，不自动执行刷写或切槽。

## 本次离线检查

临时目录 `op12_flash/CPH2581_16.0.1.300(EX01)/` 只有以下启动镜像及本地 AnyKernel3 包，没有完整固件。镜像均为 `CPH2581_16.0.1.300(EX01)` 版本官方 ROM 包中提取。

| 文件 | 大小 | Boot header | 内核大小 | AVB footer |
|---|---:|---:|---:|---|
| boot.img | 192 MiB | v4 | 35,691,008 bytes | 有 |
| init_boot.img | 8 MiB | v4 | 0 | 有 |
| recovery.img | 100 MiB | v4 | 0 | 有 |

```text
8498496a72bfa4673235ca5f5a588abe9ef2b97c52de5179208aed2957e0477d  boot.img
31647dc05f262dbdb9de23034f97334347736355b3e3d1b9f63f9ed88dc2be67  init_boot.img
5013a46a0e56511fe792b62f24485321dca86b0f681b0f6766287849a8871851  recovery.img
```

⚠️ 请注意：网上下载的镜像，通过文件名、目录名和 footer 均不能证明官方来源、签名有效或目标槽兼容。且我的机型、系统版本等未必与你相同，镜像可能无法直接使用。我建议你：**亲自下载官方 ROM 并提取**。


## 健康状态下先保存信息

记录型号、完整系统版本、当前槽及是否支持 A/B 插槽等信息。可在正常启动、ADB 可用时读取：

```bash
adb shell getprop ro.product.model
adb shell getprop ro.build.display.id
adb shell getprop ro.boot.slot_suffix
adb shell getprop ro.virtual_ab.enabled
```

留存对应地区和型号的完整官方固件及来源、版本、校验值；另存已验证的 AnyKernel3 包。启动链可能还涉及 vendor_boot、dtbo、vbmeta 及其链式分区和系统/vendor 模块。需要核对实际分区布局，不能凭三个文件推断完整清单。

没有进行中的 OTA/快照合并时，再考虑备用槽维护；有进行中的更新时先正常完成更新。Virtual A/B 的系统分区并非简单的永久双份备份，不要写一个把 A 全盘克隆到 B 的通用脚本。

## 在可用系统中备份启动分区

先仅列出存在的路径（需要手机已 root；不要在故障 Fastboot 状态下执行）：

```bash
adb shell su -c 'ls -l /dev/block/by-name/boot* /dev/block/by-name/init_boot* /dev/block/by-name/vendor_boot* /dev/block/by-name/recovery* /dev/block/by-name/dtbo* /dev/block/by-name/vbmeta*'
```

按实际存在的分区逐个备份。以下仅示范 boot_a；确认路径后，可对其他启动分区重复：

```bash
# 备份镜像到本地（通过 adb 直接保存到电脑上）
mkdir -p rescue-backup
adb exec-out su -c 'cat /dev/block/by-name/boot_a' > rescue-backup/boot_a.img

# 必须检查上条命令退出状态、输出大小，并在手机端与主机端对比 SHA256。
echo "备份退出码：$?"
stat -c '%s bytes' rescue-backup/boot_a.img
adb shell su -c 'sha256sum /dev/block/by-name/boot_a'
sha256sum rescue-backup/boot_a.img
```

哈希一致仅证明读出的内容一致；当前 boot 可能已有自定义内核，init_boot 可能已有 root 补丁，它们不等同于官方原版；因此仍建议从官方同版本 ROM 包中亲自提取。备份命令失败可能留下空文件或不完整文件，不得使用。

## 保留并验证备用槽

优先保留已验证能进入 Recovery → fastbootd 的备用槽，不要求它能启动 Android。`slot-successful` 只是状态标记，不能替代救援入口的实际验证；如需测试切槽，先确认另一槽内容与共享数据、系统和固件兼容，并准备返回原槽的方法。不要仅为测试盲目切到未知版本槽。

恢复启动镜像的命令只在确认目标槽、版本匹配及官方来源后使用。例如：当前 A 可用、B 的其余内容已确认完整兼容，而 B 仅启动镜像受损时：

```bash
# 条件示例，不是直接执行清单；官方文件路径需自行核实。
fastboot flash boot_b /path/to/verified-stock/boot.img
fastboot flash init_boot_b /path/to/verified-stock/init_boot.img

# recovery、vendor_boot、dtbo、vbmeta 等是否需要恢复，取决于实际损坏和匹配关系。
```

只修复目标槽，保留可用槽；不要默认同时刷两槽，不自动 reboot 或 set_active，不默认关闭 AVB。B 若缺少兼容的系统/vendor 内容，上述两条命令并不能使它成为可启动系统，应使用设备适用的官方完整恢复方案。

故障时，普通 fastboot 能切槽就先用普通命令；客户端切槽失败且手机仍提供可识别的 Fastboot USB 接口时，可用仓库中的 `scripts/switch_slot.py`。切槽只改变启动选择，不能修复坏槽，也不绕过 Bootloader 锁定限制。

## 更新后维护

OTA 可能写入备用槽并改变活动槽；每次升级后重新记录版本、槽位、备份校验值和恢复文件。保留可用另一槽有价值，但“两槽都有 boot 镜像”和“安装 TWRP”都不能保证可救援。

参考：[AOSP 启动分区](https://source.android.com/docs/core/architecture/partitions/generic-boot)、[A/B 槽位状态](https://source.android.com/docs/core/ota/ab)、[Virtual A/B](https://source.android.com/docs/core/ota/virtual_ab)。

## 2026-10-12 本机实测：备用 fastbootd 入口与新内核启动成功

临时目录 `op12_flash/CPH2581_16.0.1.300(EX01)/` 中的三份镜像均从当前官方 ROM 提取，为纯净镜像；新编译 KSUN 33342 的 AK3 刷入 A 槽后已成功重启。以下流程是本机当前固件的实测记录，不保证其他设备或固件具有相同行为。

### 刷内核前验证 B 槽救援入口

1. 核实分区修改历史。本次以除 boot、init_boot 外其他分区未修改为前提；若改动过其他分区，应先按设备适用的官方恢复流程恢复匹配内容。同版本完整 ROM 连续安装两次一般可作为恢复官方状态的方案，但是否覆盖两槽及所有相关分区取决于安装方式，不能仅凭安装次数认定已恢复。
2. 从正常 A 槽系统执行 `adb reboot fastboot` 进入 fastbootd，明确向 B 槽刷入当前同版本官方 `boot.img`、`init_boot.img`。本次不需要额外刷 recovery。
3. 在 fastbootd 执行 `fastboot set_active b`，确认成功，然后完全关机。
4. 用音量下 + 电源进入 Bootloader，再执行 `fastboot reboot fastboot`。本机实测：切槽后直接重启到 fastbootd 会报错；完全关机后重新进入 Bootloader 可进入。
5. 本机出现官方语言选择界面，选择后看到 fastbootd；电脑执行 `fastboot getvar is-userspace` 确认 `yes`，执行 `fastboot getvar current-slot` 确认 `b`。此时才认定备用救援入口已验证，无需启动 B 槽 Android。
6. 切回 A，按上述完全关机方式处理切槽，再启动 A 槽 Android，确认原系统正常。
7. 用支持该 AK3 的内核刷写应用或兼容 Recovery，仅安装到 A 槽，然后重启验证。AK3 ZIP 不能直接传给 `fastboot flash`；fastbootd 用于刷分区镜像。本机已确认 KernelSU Next 管理器支持安装 AK3，可使用其对应刷写入口。

### 新内核无法启动时

1. 进入 Bootloader，切到 B。普通 `fastboot set_active b` 失败时，可使用本仓库交互式切槽 Python 脚本  `scripts/switch_slot.py`；收到 OKAY 才视为指令已接受。
2. 完全关机，再按键进入 Bootloader，执行 `fastboot reboot fastboot`，通过 B 槽进入已验证的 fastbootd。
3. 明确向 A 槽刷回同版本官方 boot；必要时恢复 init_boot（覆盖已打 root 补丁的 init_boot 会丢失相应 root）。逐条确认刷写成功，保留 B 不动。
4. 切回 A，完全关机后启动，验证恢复情况，再酌情恢复 root 或重新安装已验证内核。

以上现象不足以单独确诊为 kernel panic；无启动日志时记作“刷入新内核后早期启动失败”。官方语言界面的具体阶段也不只凭外观判定，以 `is-userspace: yes` 确认 fastbootd。

## 切槽脚本查询模式（2026-10-13）

`doas python3 scripts/switch_slot.py` 在执行任何查询前询问是否检测当前槽；回车跳过并手动提供当前槽，随后提示切换另一槽并要求输入 yes。已知当前槽时推荐 `--current-slot a`（切 B）或 `--current-slot b`（切 A），不调用 fastboot。`--slot a/b` 直接指定目标槽，同样不查询、仍需确认。

自动查询与原始 Python 命令的区别是增加了 `fastboot getvar current-slot`；用户测试曾出现关机提示且槽位未改变，尚不能确认根因。若查询使 Bootloader 异常，需要恢复到可操作的 Bootloader 后，使用跳过查询模式；超时只结束电脑端查询，不能恢复手机。USB 切槽本身仍保持原命令的 reset、重新查找、接口及端点、发送与读取顺序。

脚本不再硬编码 `18d1:d00d` 或接口 `(0, 0)`：按接口 `ff/42/03` 和双向 Bulk 端点识别，仅接受唯一候选；reset 后按物理 USB 端口重新查找。VID/PID 与 USB 地址打印供核对。此检测没有发送 Fastboot getvar。
