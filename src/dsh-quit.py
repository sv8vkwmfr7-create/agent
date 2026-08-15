#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向正在运行的 dsh 桌面版发送退出信号。"""
import socket

CTRL_PORT = 3081
HOST = "127.0.0.1"
try:
    with socket.create_connection((HOST, CTRL_PORT), timeout=2) as c:
        c.sendall(b"QUIT")
    print("已发送退出信号。")
except OSError:
    print("没有正在运行的 dsh 桌面版实例。")
