#!/usr/bin/env python3
"""Detect the active slot when possible, then confirm a direct USB slot switch."""
import argparse
import re
import subprocess
import sys


def detect_slot():
    try:
        result = subprocess.run(
            ['fastboot', 'getvar', 'current-slot'], capture_output=True,
            text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'[-] 槽位查询不可用：{exc}')
        return None
    output = result.stdout + '\n' + result.stderr
    match = re.search(r'current-slot:\s*_?([ab])\b', output, re.IGNORECASE)
    if result.returncode == 0 and match:
        return match.group(1).lower()
    print('[-] 槽位查询失败或返回无法识别：', output.strip() or '无输出')
    return None


def select_target(explicit_slot=None, current_slot=None):
    if explicit_slot:
        print('[!] 已指定目标槽，跳过全部 fastboot 查询。')
        target = explicit_slot
    else:
        current = current_slot
        if current:
            print('[!] 使用你提供的当前槽，未进行设备查询。')
        else:
            print('[!] 新版脚本曾在查询路径出现 Bootloader 异常；失败或超时不能保证设备仍可操作。')
            if input('是否查询当前活动槽？输入 yes 查询，回车跳过：').strip().lower() == 'yes':
                current = detect_slot()
            if current is None:
                print('[!] 将跳过设备查询。请提供当前槽；不确定时请取消，勿猜测。')
                current = input('当前槽 a/b（回车取消）：').strip().lower()
                if current not in ('a', 'b'):
                    print('[+] 已取消，未发送切槽指令。')
                    return None
                print('[!] 当前槽来自手动输入，未经设备验证。')
        target = 'b' if current == 'a' else 'a'
        print(f'[+] 当前活动槽：{current.upper()}；将切换到另一槽：{target.upper()}。')
    print('[!] 请确认目标槽已有可用救援入口；本脚本不刷镜像、不自动重启。')
    if input(f'是否强制发送 set_active:{target} 切槽？输入 yes 确认：').strip().lower() != 'yes':
        print('[+] 已取消，未发送切槽指令。')
        return None
    return target


def find_fastboot_interfaces(usb_core):
    candidates = []
    for dev in usb_core.find(find_all=True):
        try:
            for cfg in dev:
                for intf in cfg:
                    if (intf.bInterfaceClass, intf.bInterfaceSubClass,
                            intf.bInterfaceProtocol) == (0xff, 0x42, 0x03):
                        directions = {ep.bEndpointAddress & 0x80 for ep in intf
                                      if ep.bmAttributes & 3 == 2}
                        if directions == {0, 0x80}:
                            candidates.append((dev, cfg.bConfigurationValue,
                                               intf.bInterfaceNumber,
                                               intf.bAlternateSetting))
        except usb_core.USBError as exc:
            print(f'[-] 无法读取 USB {dev.idVendor:04x}:{dev.idProduct:04x} 描述符：{exc}')
    return candidates


def choose_device(usb_core):
    candidates = find_fastboot_interfaces(usb_core)
    for dev, _, number, _ in candidates:
        print(f'[+] Fastboot 接口：{dev.idVendor:04x}:{dev.idProduct:04x} '
              f'bus={dev.bus} address={dev.address} interface={number}')
    if len(candidates) != 1:
        print('[-] 需要唯一的 Fastboot 接口。未找到时检查模式/权限；多台时请拔掉其他设备。')
        return None
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    slots = parser.add_mutually_exclusive_group()
    slots.add_argument('--slot', choices=('a', 'b'), help='明确指定目标槽，并跳过查询（仍需确认）')
    slots.add_argument('--current-slot', choices=('a', 'b'), help='提供当前槽，跳过查询并提示切到另一槽')
    args = parser.parse_args()
    try:
        import usb.core
        import usb.util
    except ImportError:
        print('[-] 缺少 PyUSB，请先安装 python-pyusb（Arch Linux）。')
        return 1

    try:
        selected = choose_device(usb.core)
        if selected is None:
            return 1
        dev, config_value, interface_number, alternate = selected
        bus, ports = dev.bus, dev.port_numbers
        if not ports:
            print('[-] 无法取得 USB 物理端口路径，拒绝 reset 后猜测设备。')
            return 1
        try:
            target = select_target(args.slot, args.current_slot)
        except (EOFError, KeyboardInterrupt):
            print('\n[+] 已取消，未发送切槽指令。')
            return 1
        if target is None:
            return 0
        try:
            dev.reset()
        except Exception:
            pass  # Preserve the original command's best-effort reset.

        # Re-find by physical USB port: address may change after reset.
        candidates = [item for item in find_fastboot_interfaces(usb.core)
                      if item[0].bus == bus and item[0].port_numbers == ports]
        if len(candidates) != 1:
            print('[-] reset 后无法唯一找到同一物理端口的 Fastboot 设备，请重新运行。')
            return 1
        dev, config_value, interface_number, alternate = candidates[0]
        dev.set_configuration(config_value)
        cfg = dev.get_active_configuration()
        intf = cfg[(interface_number, alternate)]
        if alternate:
            dev.set_interface_altsetting(interface=interface_number, alternate_setting=alternate)
        ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: (e.bmAttributes & 3) == 2 and usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: (e.bmAttributes & 3) == 2 and usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        if ep_out is None or ep_in is None:
            print('[-] 未找到 USB 输入/输出端点，未发送切槽指令。')
            return 1
        print(f'[+] 正在发送 set_active:{target} ...')
        ep_out.write(f'set_active:{target}'.encode('ascii'))
        resp = bytes(ep_in.read(64, timeout=3000))
        print('[+] 手机主板回复:', resp.decode(errors='ignore'))
        if not resp.startswith(b'OKAY'):
            print('[-] 未收到 OKAY，不能确认切槽成功。不要据此直接刷写。')
            return 1
        print(f'[+] 已收到 OKAY；这只确认指令成功，不保证 {target.upper()} 槽能够启动。')
        print('[+] 按本机实测救援流程：完全关机，再按键进入 Bootloader。')
        return 0
    except usb.core.USBError as exc:
        print(f'[-] USB 操作失败：{exc}')
        print('[!] 请检查权限、数据线及其他 fastboot 进程；若发送后读响应失败，槽位可能已改变。')
        return 1


if __name__ == '__main__':
    sys.exit(main())
