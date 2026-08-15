#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Harness —— 桌面版启动器

把 `npx @deepseek-ai/dsh web` 提供的网页版 (http://127.0.0.1:3080)
封装成一个原生 Edge WebView2 桌面窗口，并通过一个 Windows 快捷方式
的全局热键 (默认 Ctrl+Alt+D) 唤起。

特性：
  * 单实例：重复按热键会清理残留实例并重启，避免“点了没反应”。
  * 自动按需启动 dsh web 服务；若服务已在运行则直接复用。
  * 启动前自动校验 npm 缓存；若检测到缓存锁损坏（Lock compromised /
    ECOMPROMISED）会自动 `npm cache clean --force` 后重试，避免无限超时。
  * 先弹“加载中”窗口，等服务就绪后再跳转到主界面，消除启动错觉。
  * 关闭窗口时一并结束我们启动的服务进程，避免遗留僵尸 node。
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
import threading

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


def npm_cmd_path():
    c = os.path.join(NODE_DIR, "npm.cmd")
    if os.path.exists(c):
        return c
    c2 = os.path.join(NODE_DIR, "npm")
    if os.path.exists(c2):
        return c2
    return "npm"


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


def find_pid_on_port(port):
    """返回本地监听 `127.0.0.1:port` 的进程 PID，找不到返回 None。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception as e:  # noqa: BLE001
        log.warning("netstat 查询端口 %d 失败: %s", port, e)
        return None
    target = f"127.0.0.1:{port}"
    for line in out.splitlines():
        parts = line.split()
        # 典型: Proto  LocalAddress  ForeignAddress  State  PID
        if len(parts) >= 5 and parts[1] == target and parts[3] == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def pid_alive(pid):
    if not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if h:
            kernel32.CloseHandle(h)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def kill_pid(pid):
    if not pid:
        return False
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, timeout=10,
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("结束进程 PID %d 失败: %s", pid, e)
        return False


def npm_cache_verify():
    """启动前快速校验 npm 缓存，预防性修复锁损坏。失败不计为致命。"""
    try:
        env = dict(os.environ)
        env["PATH"] = NODE_DIR + os.pathsep + env.get("PATH", "")
        subprocess.run(
            [npm_cmd_path(), "cache", "verify"],
            env=env, capture_output=True, timeout=120,
        )
        log.info("npm cache verify 完成。")
    except Exception as e:  # noqa: BLE001
        log.warning("npm cache verify 跳过/失败(忽略): %s", e)


def npm_cache_heal():
    """缓存损坏时，强制清理 npm 缓存。返回是否执行成功。"""
    log.warning("检测到 npm 缓存损坏，尝试 `npm cache clean --force` 修复…")
    try:
        env = dict(os.environ)
        env["PATH"] = NODE_DIR + os.pathsep + env.get("PATH", "")
        subprocess.run(
            [npm_cmd_path(), "cache", "clean", "--force"],
            env=env, capture_output=True, timeout=180,
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("npm cache clean --force 失败: %s", e)
        return False


def server_log_has_corruption():
    """读取 dsh-server.log，判断是否为 npm 缓存锁损坏。"""
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
        markers = ("Lock compromised", "ECOMPROMISED",
                   "cache clean", "ENOTSUP", "corrupted")
        return any(m in data for m in markers)
    except Exception:
        return False


def start_server():
    """启动 dsh web 服务（后台、无窗口、日志写入 SERVER_LOG）。返回 Popen。"""
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
        cwd=APP_DIR,
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


LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #0b1f3a; color: #cfe3ff;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}
.spinner {
  width: 46px; height: 46px; margin-bottom: 18px;
  border: 5px solid rgba(255,255,255,.18); border-top-color: #4f8cff;
  border-radius: 50%; animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 8px; }
p { opacity: .7; font-size: 13px; margin: 0; max-width: 320px; text-align: center; line-height: 1.6; }
</style></head><body>
  <div class="spinner"></div>
  <h1>正在启动 DeepSeek Harness…</h1>
  <p>首次启动需从 npm 拉取 dsh 包，请稍候（最多约 1–2 分钟）。</p>
</body></html>"""

TIMEOUT_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
background:#0b1f3a;color:#ffd0d0;font-family:"Segoe UI",system-ui,sans-serif;text-align:center;padding:24px}
h1{font-size:20px;margin:0 0 10px} p{opacity:.85;font-size:13px;max-width:420px;line-height:1.7}
code{background:rgba(255,255,255,.1);padding:2px 6px;border-radius:4px}
</style></head><body>
<h1>服务启动超时</h1>
<p>dsh web 服务未能在预期时间内就绪。常见原因：<br>
1) 首次启动需要联网从 npm 拉取 dsh 包；<br>
2) npm 缓存锁损坏。可尝试在命令行执行 <code>npm cache clean --force</code> 后重新打开本程序。<br>
详细错误见同目录下的 <code>dsh-server.log</code>。</p>
</body></html>"""


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    # 1) 清理可能残留的僵尸主实例：控制端口 3081 被死进程占着会导致“点击无反应”。
    owner = find_pid_on_port(CTRL_PORT)
    if owner is not None:
        if pid_alive(owner):
            # 真有活着的实例占用端口，先尝试优雅退出让它重生
            log.info("控制端口被运行中实例 PID %d 占用，发送 QUIT 后重启。", owner)
            notify_master(b"QUIT")
            for _ in range(10):
                if find_pid_on_port(CTRL_PORT) is None:
                    break
                time.sleep(0.5)
        else:
            log.warning("控制端口被死进程 PID %d 占用，清理中。", owner)
        still = find_pid_on_port(CTRL_PORT)
        if still is not None:
            log.warning("旧实例未退出 (PID %d)，强制结束。", still)
            kill_pid(still)

    master = become_master()
    if master is None:
        log.info("成为主实例失败，发送 FOCUS 退化处理。")
        notify_master(b"FOCUS")
        return

    import webview

    running = [True]
    state = {"started_here": False, "proc": None}

    # 先弹“加载中”窗口，避免点了像没反应
    window = webview.create_window(
        "DeepSeek Harness",
        html=LOADING_HTML,
        width=1366,
        height=768,
    )

    def launch_server():
        """按需启动服务（已运行则复用）；端口被僵尸占着则先清。"""
        if not server_running():
            srv_pid = find_pid_on_port(DSH_PORT)
            if srv_pid and not server_running():
                log.warning("端口 %d 被 PID %d 占用但服务无响应，清理中。",
                            DSH_PORT, srv_pid)
                kill_pid(srv_pid)
            state["proc"] = start_server()
            state["started_here"] = True

    def wait_ready(timeout=180):
        deadline = time.time() + timeout
        while not server_running():
            if time.time() > deadline:
                return False
            time.sleep(1)
        return True

    def bootstrap():
        """后台线程：校验缓存 → 启动 → 等待；损坏则自愈重试。"""
        try:
            npm_cache_verify()
        except Exception:  # noqa: BLE001
            pass

        launch_server()

        if not wait_ready():
            # 首次未就绪：若日志显示缓存损坏，自动修复后重试一次
            if server_log_has_corruption():
                log.warning("服务未就绪且疑似 npm 缓存损坏，准备自愈重试。")
                if state["proc"] is not None:
                    try:
                        state["proc"].kill()
                    except Exception:  # noqa: BLE001
                        pass
                    state["proc"] = None
                    state["started_here"] = False
                npm_cache_heal()
                launch_server()
                wait_ready()

        if server_running():
            try:
                window.load_url(f"http://{DSH_HOST}:{DSH_PORT}")
                log.info("dsh web 已就绪: http://%s:%d", DSH_HOST, DSH_PORT)
            except Exception as e:  # noqa: BLE001
                log.warning("跳转到主界面失败: %s", e)
        else:
            try:
                window.load_html(TIMEOUT_HTML)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=bootstrap, daemon=True).start()

    def on_loaded():
        """窗口加载完成后监听控制端口（FOCUS / QUIT）。"""
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
        # 若服务是我们启动的，关闭窗口时一并结束，避免遗留僵尸 node 进程。
        if state["started_here"] and state["proc"] is not None:
            try:
                state["proc"].terminate()
                try:
                    state["proc"].wait(timeout=5)
                except Exception:  # noqa: BLE001
                    state["proc"].kill()
            except Exception as e:  # noqa: BLE001
                log.warning("终止 dsh web 服务失败: %s", e)
        log.info("窗口已关闭，退出桌面版。")


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
