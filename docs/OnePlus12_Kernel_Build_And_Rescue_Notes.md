# 一加 12 (SM8650) 自定义内核编译与切槽救砖记录

> **设备型号**：OnePlus 12 (CPH2581 / 高通骁龙 8 Gen 3)  
> **内核架构**：Android 14 GKI 2.0 (Linux 6.1.118-android14-11)  
> **核心诉求**：解除原厂硬编码阉割的 `CONFIG_USER_NS` 以运行 DroidSpace 容器沙箱，集成 KernelSU Next 原生 Root 及 BBR / ZRAM ZSTD 等性能调优。  
> **救砖核心突破**：在异常 Fastboot 状态下直接发送 USB 切槽指令，借助仍可用的 B 槽恢复启动；故障内部机制尚未证实。

---

## 目录
- [一、背景与核心诉求](#一背景与核心诉求)
- [二、第一阶段：编译管线的暗坑与自愈补丁](#二第一阶段编译管线的暗坑与自愈补丁)
- [三、第二阶段：首次刷写崩溃的终极“病理复盘”](#三第二阶段首次刷写崩溃的终极病理复盘)
- [四、第三阶段：救砖死局 —— ABL“高危锁死态”深度剖析](#四第三阶段救砖死局--abl高危锁死态深度剖析)
- [五、第四阶段：绝杀突围 —— 为什么只有 Python 切 B 槽能破局？](#五第四阶段绝杀突围--为什么只有-python-切-b-槽能破局)
- [六、第五阶段：借道修复与备用槽维护](#六第五阶段借道修复与备用槽维护)
- [附录：高频紧急救砖命令备忘录](#八附录高频紧急救砖命令备忘录)

---

## 一、背景与核心诉求

### 1. 为什么必须编译内核（无法仅靠模块注入）？
真机提取的 `my_defconfig` 明确显示：
```ini
CONFIG_NAMESPACES=y
# CONFIG_USER_NS is not set      <--- 厂商默认关闭！
CONFIG_OVERLAY_FS=y
```
厂商为过 Google CTS 安全认证关闭了 `CONFIG_USER_NS`（用户命名空间）。DroidSpace 多开容器依赖非 root 映射独立的 UID/GID，该特性属于 Linux 调度器核心，**无法通过 LKM 动态内核模块注入，必须在源码级别重编 GKI 内核**。

### 2. 真实版本号严密对齐
通过对官方底包执行 `strings boot.img` 提取出出厂真实的绝对身份标识：
* **Linux 基线版本**：`6.1.118`
* **完整 Vermagic / 签名串**：`6.1.118-android14-11-o-gac2e718ebee6`
* **编译器版本**：Android Clang 17.0.2 / LLD 17.0.2

---

## 二、第一阶段：编译管线的暗坑与自愈补丁

### 1. 废弃的 LLVM 后端参数崩溃
* **报错**：`clang: Unknown command line argument '-no-type-based-alias-analysis'`
* **原因**：Clang 17 废弃了该参数。Linux 内核默认已自带 `-fno-strict-aliasing`，无需且严禁在 `KCFLAGS` 中强行传入已废弃的后端参数。
* **修复**：彻底清除 `KCFLAGS`。

### 2. 一加未开源专有目录引发构建中断
* **报错**：`make[5]: *** No rule to make target '../drivers/soc/oplus/boot/Makefile'. Stop.`
* **原因**：一加在开源树中删除了部分专有闭源目录，只留下失效软链接。构建系统扫描到上层 Makefile 引用的子目录不存在时直接抛出 Error 2。
* **修复（全自动 Makefile 扫描自愈）**：
  在编译前执行自动化递归扫描，为所有被引用但缺失的子目录生成空 Makefile 存根：
  ```bash
  mkdir -p drivers/soc/oplus/boot && touch drivers/soc/oplus/boot/Makefile
  find . -type f \( -name "Makefile*" -o -name "Kbuild*" \) -exec grep -EH '^\s*obj-.*\+=\s*[^/]+/' {} + | while IFS=':' read -r mk line; do
    dir=$(dirname "$mk")
    items=$(echo "$line" | sed -e 's/.*+=\s*//' -e 's/#.*//')
    for item in $items; do
      if [[ "$item" == */ ]]; then
        sub_dir="$dir/$item"
        if [ ! -f "${sub_dir}Makefile" ] && [ ! -f "${sub_dir}Kbuild" ]; then
          mkdir -p "$sub_dir" && touch "${sub_dir}Makefile"
        fi
      fi
    done
  done
  ```

---

## 三、第二阶段：首次刷写崩溃的“病理复盘”

在 GitHub Actions 顺利产出内核 `Image` 后，我在 PC 端使用 `magiskboot` 手工替换并重打包了 `new_boot.img`，刷入后**手机死死定格在 Orange State（5 秒警告）**，无任何屏幕刷新或开机动画反应。

### 已观察到的现象与尚未证实的原因

重打包时工具输出出现 VBMETA 差异，刷入后停在 Orange State。AVB 元数据变化、镜像格式、内核启动失败或厂商模块不匹配都值得排查，但现有记录不足以确认执行停在 ABL，也不足以确认 AVB 就是唯一根因。没有串口日志、pstore/ramoops 或相关源码证据时，不把停在警告画面等同于已证明的 Bootloader 锁死。

---

## 四、第三阶段：异常 Fastboot 状态的实测记录

当时出现以下现象：

- 下载镜像报 `Requested download size is more than max allowed`。
- 查询 `max-download-size` 时出现 `Press any key to shutdown`。
- 部分分区查询返回大小 0。
- `fastboot boot` 卡住；普通客户端 `set_active b` 报 `Device does not support slots`。

这些现象不能单独证明下载缓冲区分配为 NULL、分区句柄被冻结，或一加某代平台普遍不支持 `fastboot boot`。槽位 bootable/successful/retry 状态与分区是否可写也不是同一个概念。

后来直接发送 `set_active:b` 收到 `OKAY`，并借助 B 槽恢复。这是本次实际验证有效的救援路径，不代表所有故障都只有这一种解决方法。

---

## 五、第四阶段：直接发送切 B 槽指令

前提是手机仍能枚举为对应 USB Fastboot 设备，而且 B 槽已有可启动的兼容内容。直接发送指令绕过客户端检查，不会绕过手机端权限或修复损坏镜像；`OKAY` 也不保证目标槽能开机。

### 1. Python 裸协议直连突破
Fastboot 本质是明文 USB 文本协议。PC 客户端虽然被卡死，但手机芯片依然在监听 `set_active` 指令。
我们用 Python 绕过 PC 工具的检查，直接发送 `set_active:b` 的 12 个字节：

```python
import usb.core, usb.util

# 抓取 18d1:d00d 硬件设备
dev = usb.core.find(idVendor=0x18d1, idProduct=0xd00d)
dev.set_configuration()
cfg = dev.get_active_configuration()
intf = cfg[(0, 0)]
ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

# 绕过 PC 工具，直接硬塞 12 字节底层原生指令
ep_out.write(b'set_active:b')
print('手机回复:', bytes(ep_in.read(64, timeout=3000)).decode(errors='ignore'))
```
手机主板当场回复：**`OKAY`**！这是整场战役的决定性转折点。

### 2. 幸好 B 槽未动（借东风破局）
* 整个折腾过程中，所有的污染和崩溃全部发生在 A 槽；
* **B 槽当时可用，查询曾显示 `slot-successful:b: yes`；标记本身不能证明全部分区内容完好**；
* 切换到 B 槽后恢复启动，并成功进入 **`fastbootd`**；此前异常不再阻止后续操作。内部状态如何变化尚无证据。

---

## 六、第五阶段：借道修复与备用槽维护

以下是当时执行成功的历史记录，不是每次救砖都应照抄的通用步骤。`fastbootd` 的可刷分区仍受设备实现限制；恢复损坏槽时，应保留已验证可用的另一槽。

```bash
# 1. 彻底恢复真实主系统 A 槽 (201MB 大镜像在 fastbootd 下秒刷)
fastboot flash boot_a stock_boot.img
fastboot flash init_boot_a stock_init_boot.img

# 2. 当时也刷了 B 槽（会覆盖已有救援内容，不建议默认重复）
fastboot flash boot_b stock_boot.img
fastboot flash init_boot_b stock_init_boot.img

# 3. 回到真正的家园 A 槽，启动！
fastboot set_active a
fastboot reboot
```
**结果**：手机完美开机进入桌面，所有应用、聊天记录、个人数据 **100% 毫发无损**！

---

## 附录：高频紧急救砖命令备忘录

### 场景 1：手机黑屏或卡死，冷启动强回 Fastboot
1. 拔掉数据线，长按 **【音量加键】 + 【电源键】 10 秒** 强行断电关机。
2. 彻底黑屏后，**长按【音量减键】不放，插上连着电脑的数据线**。
3. 亮起绿字 `FASTBOOT MODE` 时立刻松手。

### 场景 2：在 Fastboot 界面无脑进 Recovery
按 **【音量减键】** 将屏幕顶部大方框切换为红色的 **`Recovery mode`**，按 **【电源键】** 确认即可进入。

### 场景 3：普通 fastboot 客户端切槽失败

在仓库根目录运行：

```bash
doas python3 scripts/switch_slot.py
```

脚本保留 reset、重新查找设备、直接发送切槽指令和 3 秒读取超时；按 Fastboot 接口识别设备和 Bulk 端点，不再硬编码 VID/PID 或接口编号。切槽指令按所选目标生成。查询前先询问；跳过或失败时手动提供当前槽，再提示切换另一槽。可用 `--current-slot a/b` 提供当前槽而不查询。可加 `--slot b` 或 `--slot a` 跳过查询；均须输入 yes 确认，不刷写、不自动重启。

### 第三方 Recovery 不是独立救援保证

本机实测：部分内核启动故障发生后，即使刷入 TWRP 也无法进入 Recovery，需要借助仍可用的另一槽。不能认为“有 TWRP 就可以放心刷”。这也不意味着所有 kernel panic 都必然无法进入 Recovery。

临时目录中的 `recovery.img` 为 boot header v4，kernel size 为 0；它不是自带内核的完整独立救援镜像。Recovery 的内核及 vendor ramdisk 如何组合需结合设备实现核对。[AOSP 启动分区说明](https://source.android.com/docs/core/architecture/partitions/generic-boot)

### 备用槽与离线镜像准备

具体步骤见 [备用槽准备流程](OP12_Rescue_Preparation.md)。保留一个已实测可用的槽，不把“只刷入几个官方启动镜像”当作完整系统备份；OTA 后重新核对槽位及版本，备用槽不会永久不变。[AOSP A/B 状态说明](https://source.android.com/docs/core/ota/ab)

---
*本记录用于保存这台设备的实测经历；未经日志或源码验证的内部机制不作为定论。*

## 2026-10-12 更新：备用槽实测与新内核成功启动

新构建的 KSUN 33342 AK3 在 A 槽刷入后已成功重启。临时目录的三份镜像均为当前官方 ROM 提取的纯净镜像。

本次验证 B 槽救援入口时仅恢复官方 boot、init_boot；切到 B 后必须先完全关机，再通过按键进入 Bootloader，执行 `fastboot reboot fastboot` 才成功进入 fastbootd。切槽后直接重启到 fastbootd 的尝试曾报错。此步骤是本机当前固件的实测经验。

完整准备和恢复步骤见 [备用槽准备流程中的实测记录](OP12_Rescue_Preparation.md#2026-10-12-本机实测备用-fastbootd-入口与新内核启动成功)。目标是保留已验证能进入 fastbootd 的 B 槽，不要求 B 能启动 Android；仅向 A 安装新内核。AK3 ZIP 应由支持它的刷写工具安装，fastboot flash 无法直接刷 AK3 ZIP。
