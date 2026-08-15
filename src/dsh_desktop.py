#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Harness —— 桌面版启动器

把 `npx @deepseek-ai/dsh web` 提供的网页版 (http://127.0.0.1:3080)
封装成一个原生 Edge WebView2 桌面窗口，并通过一个 Windows 快捷方式
的全局热键 (默认 Ctrl+Alt+D) 唤起。

特性：
  * 单实例：重复按热键不会开多个窗口，而是聚焦已存在的窗口。
  * 自动按需启动 dsh web 服务；若服务已在运行则直接复用。
  * 支持通过本目录下的 .env 文件注入环境变量 (如 DEEPSEEK_API_KEY)。
  * 控制端口 3081 用于实例间通信 (FOCUS / QUIT)。

用法：
  直接双击由安装脚本生成的快捷方式，或运行：
      pythonw dsh_desktop.py
"""

import os
import sys
import time
import socket
import subprocess
import logging

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
# 区分“冻结运行时”（PyInstaller 打包）和开发运行：只读资源走 BASE_DIR，
# 日志 / .env 等可写文件走 APP_DIR（exe 所在目录）。
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = HERE
    APP_DIR = HERE

DSH_HOST = os.environ.get("DSH_WEB_HOST", "127.0.0.1")
DSH_PORT = int(os.environ.get("DSH_WEB_PORT", "3080"))
CTRL_PORT = 3081
HOTKEY = "Ctrl+Alt+D"
# Node 位置：优先用环境变量覆盖；否则从 PATH 找 npx；再退到 exe 旁边的 node 文件夹；最后退回 PATH。
import shutil
NODE_DIR = os.environ.get("DSH_NODE_DIR")
if not NODE_DIR:
    _npx = shutil.which("npx.cmd") or shutil.which("npx") \
        or shutil.which("node.exe") or shutil.which("node")
    if _npx:
        NODE_DIR = os.path.dirname(_npx)
    else:
        NODE_DIR = os.path.join(APP_DIR, "node")  # 允许自带 node 文件夹
NPX = os.path.join(NODE_DIR, "npx.cmd")
if not os.path.exists(NPX):
    NPX = os.path.join(NODE_DIR, "npx")
if not os.path.exists(NPX):
    NPX = "npx"  # 最后的兜底：交给 PATH
LOG_FILE = os.path.join(APP_DIR, "dsh-desktop.log")
SERVER_LOG = os.path.join(APP_DIR, "dsh-server.log")
ENV_FILE = os.path.join(APP_DIR, ".env")
# 窗口 / 任务栏图标（DeepSeek 官方蓝鲸）
ICON_PATH = os.path.join(BASE_DIR, "assets", "deepseek-whale.ico")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("dsh-desktop")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def load_dotenv(path):
    """极简 .env 解析，返回 dict（不覆盖已有环境变量）。"""
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k:
                    env[k] = v
    return env


def server_running():
    try:
        with socket.create_connection((DSH_HOST, DSH_PORT), timeout=1.5):
            return True
    except OSError:
        return False


def start_server():
    """启动 dsh web 服务（后台、无窗口、日志写入 SERVER_LOG）。"""
    env = dict(os.environ)
    # 让 npx / node 在 PATH 中可用
    env["PATH"] = NODE_DIR + os.pathsep + env.get("PATH", "")
    # 注入 .env 中的变量（仅当原环境没有时）
    for k, v in load_dotenv(ENV_FILE).items():
        env.setdefault(k, v)

    log.info("启动 dsh web 服务: %s -y @deepseek-ai/dsh web", NPX)
    f = open(SERVER_LOG, "a", encoding="utf-8")
    # 用 cmd /c 运行 npx.cmd，避免直接执行 .cmd 的兼容问题；
    # CREATE_NO_WINDOW 抑制子进程黑色控制台窗口。
    cmd_exe = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [cmd_exe, "/c", NPX, "-y", "@deepseek-ai/dsh", "web"],
        env=env,
        cwd=HERE,
        stdout=f,
        stderr=f,
        creationflags=flags,
    )
    return proc


def become_master():
    """尝试成为主实例（绑定控制端口）。失败返回 None。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((DSH_HOST, CTRL_PORT))
        s.listen(8)
    except OSError as e:
        log.info("无法绑定控制端口 %d: %s", CTRL_PORT, e)
        return None
    return s


def notify_master(msg=b"FOCUS"):
    try:
        with socket.create_connection((DSH_HOST, CTRL_PORT), timeout=2) as c:
            c.sendall(msg)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    master = become_master()
    if master is None:
        # 已有实例：发送聚焦请求后退出
        log.info("检测到已有实例，发送 FOCUS。")
        notify_master(b"FOCUS")
        return

    # 确保服务运行
    started_here = False
    if not server_running():
        start_server()
        started_here = True

    deadline = time.time() + 180
    while not server_running():
        if time.time() > deadline:
            log.error("服务在超时时间内未启动，请查看 %s", SERVER_LOG)
            return
        time.sleep(1)
    log.info("dsh web 已就绪: http://%s:%d", DSH_HOST, DSH_PORT)

    import webview

    running = [True]
    window = webview.create_window(
        "DeepSeek Harness",
        url=f"http://{DSH_HOST}:{DSH_PORT}",
        width=1366,
        height=768,
    )

    def on_loaded():
        """在 pywebview 后台线程中监听控制端口。"""
        master.settimeout(1.0)
        while running[0]:
            try:
                conn, _ = master.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = conn.recv(1024).strip()
                if data == b"FOCUS":
                    try:
                        window.restore()
                        window.show()
                    except Exception as e:  # noqa: BLE001
                        log.warning("聚焦窗口失败: %s", e)
                elif data == b"QUIT":
                    try:
                        window.destroy()
                    except Exception:  # noqa: BLE001
                        pass
                    running[0] = False
            finally:
                conn.close()
        try:
            master.close()
        except OSError:
            pass

    try:
        webview.start(
            on_loaded,
            icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
        )
    finally:
        running[0] = False
        log.info("窗口已关闭，退出桌面版。")
        # 若服务是我们启动的，可选择一并终止。为方便复用，这里保留服务进程。


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log.exception("启动失败: %s", e)
        # 尽量给用户一个可见提示
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0, f"DeepSeek Harness 桌面版启动失败：\n{e}", "dsh-desktop", 0x10
            )
        except Exception:
            pass
