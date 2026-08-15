#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 DeepSeek Harness 桌面版生成带全局热键的桌面快捷方式。

用法：把本脚本放到 DeepSeekHarness 文件夹里（和 DeepSeekHarness.exe 同级），
直接运行：  python create-shortcut.py
会在桌面创建「DeepSeek Harness.lnk」，并绑定 Ctrl+Alt+D。
"""
import os
import sys
import pythoncom
from win32com.shell import shell

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "DeepSeekHarness.exe")
if not os.path.exists(EXE):
    print("未找到 DeepSeekHarness.exe，请把本脚本放在它旁边。")
    sys.exit(1)

# Hotkey WORD: 高位 = 修饰键(CONTROL=0x02, ALT=0x04, SHIFT=0x01)，低位 = 虚拟键码 'D'=0x44
HOTKEY = (0x06 << 8) | 0x44  # Ctrl + Alt + D

link = os.path.join(os.environ["USERPROFILE"], "Desktop", "DeepSeek Harness.lnk")
sl = pythoncom.CoCreateInstance(
    shell.CLSID_ShellLink, None,
    pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
sl.SetPath(EXE)
sl.SetArguments("")
sl.SetWorkingDirectory(HERE)
sl.SetDescription("DeepSeek Harness 桌面版 (Ctrl+Alt+D)")
sl.SetIconLocation(EXE, 0)
sl.SetHotkey(HOTKEY)
sl.SetShowCmd(1)  # 正常窗口
pf = sl.QueryInterface(pythoncom.IID_IPersistFile)
pf.Save(link, 0)
print("已创建快捷方式:", link)
print("热键: Ctrl + Alt + D")
