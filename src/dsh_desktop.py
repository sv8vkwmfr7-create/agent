#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Harness —— 桌面版启动器

把 `@deepseek-ai/dsh web` 提供的网页版 (http://127.0.0.1:3080)
封装成一个原生 Edge WebView2 桌面窗口，并通过一个 Windows 快捷方式
的全局热键 (默认 Ctrl+Alt+D) 唤起。

设计要点（含 2026-08-15 启动问题改进）：
  * 单实例：重复按热键会聚焦已有窗口 / 清理残留实例，避免“点了没反应”。
  * 优先使用安装包内自带的 Node (DeepSeekHarness\\node)，不再依赖系统 Node，
    消除不同用户 Node/npm 版本、缓存、代理差异（P0-2）。
  * 优先使用安装包内随附的 dsh (DeepSeekHarness\\app)，首启不再联网从 npm 拉取；
    仅当本地 dsh 缺失时回退到 npx（P0-1）。
  * 本地模式直接用 node 跑 dsh bin，进程链上无 cmd.exe；服务进程以
    CREATE_NO_WINDOW | DETACHED_PROCESS 启动，全程无终端窗口。
  * 服务已在运行时直接复用（秒开）；npm 缓存校验仅 npx 联网模式执行（本地模式跳过，
    省去每次启动约 10s 的 cache verify 扫描）。
  * 启动前自动校验 npm 缓存；若检测到缓存锁损坏（Lock compromised /
    ECOMPROMISED）会自动 `npm cache clean --force` 后重试，避免无限超时（P1-6）。
  * 严格串行启动，单实例锁防并发抢 npm 缓存锁（P1-4）。
  * 自适应超时：本地模式短超时，npx 模式首启长超时（P1-5）。
  * 先弹“加载中”窗口并显示真实状态文案，消除启动错觉（P1-3）。
  * 失败时在窗口内给出可见错误 + “打开日志目录”按钮，而非空转（P1-6）。
  * 启动前检测 WebView2 运行时，缺失时弹中文指引而非静默崩溃。
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

# Node 位置：优先用环境变量覆盖；否则优先用 exe 旁边的 node 文件夹（自带 Node）；
# 最后才退回 PATH 上的系统 Node。这一优先级修正了“实际走了系统 Node”的问题（P0-2）。
NODE_DIR = os.environ.get("DSH_NODE_DIR")
if not NODE_DIR:
    _bundled = os.path.join(APP_DIR, "node")
    if os.path.isdir(_bundled) and (
        os.path.exists(os.path.join(_bundled, "npx.cmd"))
        or os.path.exists(os.path.join(_bundled, "npx"))
        or os.path.exists(os.path.join(_bundled, "node.exe"))
    ):
        NODE_DIR = _bundled
    else:
        import shutil
        _npx = shutil.which("npx.cmd") or shutil.which("npx") \
            or shutil.which("node.exe") or shutil.which("node")
        NODE_DIR = os.path.dirname(_npx) if _npx else _bundled

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
APP_NODE_MODULES = os.path.join(APP_DIR, "app", "node_modules")
LOCAL_DSH_PKG = os.path.join(APP_NODE_MODULES, "@deepseek-ai", "dsh")


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

# 本程序是无控制台的 GUI 应用：任何 subprocess.run 运行控制台命令
# （netstat/taskkill/npm）都必须带 CREATE_NO_WINDOW，否则 Windows 会
# 为子进程弹出一个可见的终端窗口（初始化时的“终端闪现”根因）。
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_hidden(args, **kwargs):
    """运行控制台命令但不弹终端窗口。"""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _NO_WINDOW_FLAGS
    return subprocess.run(args, **kwargs)


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
        out = run_hidden(
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
        run_hidden(
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
        run_hidden(
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
        run_hidden(
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


def local_dsh_present():
    """安装包内是否已随附 dsh（首启无需联网）。"""
    bin_cmd = os.path.join(APP_NODE_MODULES, ".bin", "dsh.cmd")
    bin_sh = os.path.join(APP_NODE_MODULES, ".bin", "dsh")
    return os.path.isdir(LOCAL_DSH_PKG) or os.path.exists(bin_cmd) or os.path.exists(bin_sh)


def resolve_dsh(force_npx=False):
    """
    返回 (cmd_list, label, needs_network)。
      - 优先本地 app 安装，且直接用 node 跑 package bin（不走 .cmd shim，
        从进程链上彻底移除 cmd.exe，杜绝终端窗口）（Needs_network=False）；
      - force_npx 或本地缺失时回退 npx -y（Needs_network=True）。
    """
    if not force_npx and local_dsh_present():
        entry = _dsh_bin_entry()
        if entry:
            node_exe = os.path.join(NODE_DIR, "node.exe")
            if not os.path.exists(node_exe):
                node_exe = "node"
            return [node_exe, entry, "web"], "local:node dsh bin", False
        bin_cmd = os.path.join(APP_NODE_MODULES, ".bin", "dsh.cmd")
        bin_sh = os.path.join(APP_NODE_MODULES, ".bin", "dsh")
        if os.path.exists(bin_cmd):
            return [bin_cmd, "web"], "local:app dsh.cmd", False
        if os.path.exists(bin_sh):
            return [bin_sh, "web"], "local:app dsh(sh)", False
    return [NPX, "-y", "@deepseek-ai/dsh", "web"], "npx -y @deepseek-ai/dsh", True


def _dsh_bin_entry():
    """读取本地 dsh 包的 bin 入口绝对路径（用于 node 直接启动）。"""
    try:
        import json
        pkg = os.path.join(LOCAL_DSH_PKG, "package.json")
        with open(pkg, encoding="utf-8") as f:
            data = json.load(f)
        bin = data.get("bin", {})
        rel = bin.get("dsh") or (list(bin.values())[0] if isinstance(bin, dict) and bin else None)
        if rel:
            return os.path.join(LOCAL_DSH_PKG, rel)
    except Exception:  # noqa: BLE001
        pass
    return None


def start_server(cmd, label, state):
    """启动 dsh web 服务（后台、无窗口、日志写入 SERVER_LOG）。返回 Popen。"""
    env = dict(os.environ)
    # 让 npx / node 在 PATH 中可用（优先捆绑 Node）
    env["PATH"] = NODE_DIR + os.pathsep + env.get("PATH", "")
    # 注入 .env 中的变量（仅当原环境没有时）
    for k, v in load_dotenv(ENV_FILE).items():
        env.setdefault(k, v)
    # 记录环境信息到日志首行，便于排障（P2-8）
    log.info("DSH_NODE_DIR=%s npm=%s 本地dsh=%s",
             NODE_DIR, _npm_ver(), "是" if local_dsh_present() else "否")

    log.info("启动 dsh web 服务 [%s]: %s", label, " ".join(cmd))
    f = open(SERVER_LOG, "a", encoding="utf-8")
    # 完全无窗口启动：CREATE_NO_WINDOW 不分配控制台 + DETACHED_PROCESS 不继承父控制台，
    # 从根上杜绝任何终端窗口闪现；子进程（如 dsh 的沙箱 shell）继承隐藏控制台。
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    # .cmd/.bat 才需要 cmd /c 包装；node.exe 等可执行文件直接运行，进程链更干净。
    first = cmd[0].lower()
    if first.endswith(".cmd") or first.endswith(".bat"):
        cmd_exe = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
        )
        run = [cmd_exe, "/c", *cmd]
    else:
        run = list(cmd)
    proc = subprocess.Popen(
        run,
        env=env,
        cwd=APP_DIR,
        stdout=f,
        stderr=f,
        creationflags=flags,
    )
    state["proc"] = proc
    state["started_here"] = True
    state["label"] = label
    return proc


def _npm_ver():
    try:
        env = dict(os.environ)
        env["PATH"] = NODE_DIR + os.pathsep + env.get("PATH", "")
        out = run_hidden(
            [npm_cmd_path(), "--version"],
            env=env, capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        return out or "?"
    except Exception:  # noqa: BLE001
        return "?"


# --------------------------------------------------------------------------- #
# WebView2 运行时检测（缺失则弹中文指引，而非静默崩溃）
# --------------------------------------------------------------------------- #
def webview2_available():
    """检测本机是否安装 Microsoft Edge WebView2 运行时。"""
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return True  # 非 Windows 或无法检测时不阻断
    keys = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as k:
                pv = winreg.QueryValueEx(k, "pv")[0]
                if pv:
                    return True
        except OSError:
            continue
    return False


def show_webview2_missing():
    import ctypes
    msg = (
        "DeepSeek Harness 需要 Microsoft Edge WebView2 运行时，但本机未检测到。\n\n"
        "请按以下步骤安装后重新打开本程序：\n"
        "1. 打开浏览器访问：\n"
        "   https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/\n"
        "2. 点击「下载」→ 选择「WebView2 Runtime 独立安装程序」\n"
        "3. 安装完成后，重新双击 DeepSeekHarness.exe\n\n"
        "（Windows 10/11 通常已自带；若缺失，多为精简版系统或长期未更新。）"
    )
    ctypes.windll.user32.MessageBoxW(
        0, msg, "DeepSeek Harness - 缺少 WebView2 运行时", 0x10
    )


# --------------------------------------------------------------------------- #
# 窗口内容
# --------------------------------------------------------------------------- #
def loading_html(needs_network):
    if needs_network:
        tip = ("首次启动需联网从 npm 拉取 dsh 包，请稍候（约 1–3 分钟，取决于网速）。\n"
               "请勿关闭本窗口；若长时间无响应，可查看同目录 dsh-server.log。")
    else:
        tip = "正在初始化 DeepSeek Harness，请稍候…"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; }}
body {{
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #0b1f3a; color: #cfe3ff;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}}
.spinner {{
  width: 46px; height: 46px; margin-bottom: 18px;
  border: 5px solid rgba(255,255,255,.18); border-top-color: #4f8cff;
  border-radius: 50%; animation: spin 1s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 8px; }}
p {{ opacity: .75; font-size: 13px; margin: 0; max-width: 360px; text-align: center; line-height: 1.6; white-space: pre-line; }}
</style></head><body>
  <div class="spinner"></div>
  <h1>正在启动 DeepSeek Harness…</h1>
  <p>{tip}</p>
</body></html>"""


def error_html():
    return """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
background:#0b1f3a;color:#ffd0d0;font-family:"Segoe UI",system-ui,sans-serif;text-align:center;padding:24px}
h1{font-size:20px;margin:0 0 10px} p{opacity:.85;font-size:13px;max-width:440px;line-height:1.7;margin:0 0 18px}
code{background:rgba(255,255,255,.1);padding:2px 6px;border-radius:4px}
button{font-size:14px;padding:10px 18px;border:0;border-radius:8px;cursor:pointer;
background:#4f8cff;color:#fff;font-weight:600}
button:hover{background:#3f7bef}
</style></head><body>
<h1>启动失败</h1>
<p>dsh web 服务未能启动。常见原因：<br>
1) 首次启动需要联网从 npm 拉取 dsh 包；<br>
2) npm 缓存锁损坏（已尝试自动修复仍未成功）。<br><br>
可尝试：① 检查网络后重试；② 以管理员身份运行一次 <code>npm cache clean --force</code>；
③ 点击下方按钮打开日志目录查看 <code>dsh-server.log</code>。</p>
<button onclick="window.pywebview.api.open_log_folder()">打开日志目录</button>
</body></html>"""


class JsApi:
    def open_log_folder(self):
        try:
            os.startfile(APP_DIR)
        except Exception as e:  # noqa: BLEUIDE
            log.warning("打开日志目录失败: %s", e)


# --------------------------------------------------------------------------- #
# 控制端口（单实例 / 热键通信）
# --------------------------------------------------------------------------- #
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
    # 0) WebView2 运行时检测（缺失则弹窗引导，避免静默崩溃）
    if not webview2_available():
        log.warning("未检测到 WebView2 运行时，引导用户安装。")
        show_webview2_missing()
        return

    # 1) 清理可能残留的僵尸主实例：控制端口 3081 被死进程占着会导致“点击无反应”。
    owner = find_pid_on_port(CTRL_PORT)
    if owner is not None:
        if pid_alive(owner):
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
    state = {"started_here": False, "proc": None, "label": ""}

    # 先决定模式（无需起服务即可判断），用于加载文案
    _cmd0, _label0, needs_network = resolve_dsh()
    window = webview.create_window(
        "DeepSeek Harness",
        html=loading_html(needs_network),
        width=1366,
        height=768,
        js_api=JsApi(),
    )

    def launch_server(state):
        """按需启动服务（已运行则复用）；端口被僵尸占着则先清。严格串行。"""
        if server_running():
            return True
        srv_pid = find_pid_on_port(DSH_PORT)
        if srv_pid and not server_running():
            log.warning("端口 %d 被 PID %d 占用但服务无响应，清理中。",
                        DSH_PORT, srv_pid)
            kill_pid(srv_pid)
        cmd, label, _ = resolve_dsh()
        start_server(cmd, label, state)
        return False

    def wait_ready(timeout):
        deadline = time.time() + timeout
        while not server_running():
            if time.time() > deadline:
                return False
            time.sleep(1)
        return True

    def goto_main():
        try:
            window.load_url(f"http://{DSH_HOST}:{DSH_PORT}")
            log.info("dsh web 已就绪: http://%s:%d", DSH_HOST, DSH_PORT)
        except Exception as e:  # noqa: BLE001
            log.warning("跳转到主界面失败: %s", e)

    def bootstrap():
        """后台线程：服务已运行则秒开复用；本地模式跳过 npm 校验（省 ~10s）；
        启动 → 等待；损坏则自愈重试；再失败给可见错误。"""
        # 服务已在运行（上次窗口关闭后保留）→ 直接打开主界面，跳过一切初始化
        if server_running():
            log.info("dsh web 服务已在运行，直接复用（跳过初始化）。")
            goto_main()
            return

        # npm 缓存校验仅在 npx 联网模式有意义；本地模式不碰 npm 缓存，跳过
        if needs_network:
            try:
                npm_cache_verify()
            except Exception:  # noqa: BLE001
                pass

        launched = launch_server(state)
        if launched:
            goto_main()
            return

        # 本地模式短超时，npx 模式首启长超时（P1-5）
        timeout = 180 if not needs_network else 600
        if wait_ready(timeout):
            goto_main()
            return

        # 未就绪：疑似缓存锁损坏 → 自动修复后重试一次（P1-6）
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
            launch_server(state)
            if wait_ready(timeout):
                goto_main()
                return

        # 本地 dsh 启动失败 → 回退 npx 再试一次
        if not needs_network and state.get("label", "").startswith("local"):
            log.warning("本地 dsh 启动失败，回退到 npx 再试一次。")
            if state["proc"] is not None:
                try:
                    state["proc"].kill()
                except Exception:  # noqa: BLE001
                    pass
                state["proc"] = None
                state["started_here"] = False
            cmd, label, _ = resolve_dsh(force_npx=True)
            start_server(cmd, label, state)
            if wait_ready(600):
                goto_main()
                return

        # 彻底失败 → 显示可见错误页 + 打开日志按钮（P1-6）
        log.error("服务在超时时间内未启动，展示错误页。")
        try:
            window.load_html(error_html())
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
        # 窗口关闭后保留 dsh web 服务，下次启动秒开复用（README 既定行为）；
        # 需要彻底退出时运行 dsh-quit.py。
        log.info("窗口已关闭，退出桌面版（dsh web 服务保留，下次启动更快）。")


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
