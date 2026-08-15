# 从源码构建 DeepSeek Harness 桌面版

本文说明如何把 `dsh_desktop.py` 打包成一个独立、无控制台窗口、内嵌蓝鲸图标的 Windows 可执行文件（`DeepSeekHarness.exe`）。预编译包 `DeepSeekHarness-win64.zip` 就是这么来的。

> 如果你只是想「下载就能用」，请直接去仓库 **Releases** 下载 `DeepSeekHarness-win64.zip`，不用看这篇。

---

## 1. 环境要求

- **Windows 10/11**（需要 Edge WebView2，Win10 21H2+ 一般已自带；没有的话去微软官网装 "Microsoft Edge WebView2 Runtime"）。
- **Python 3.13**（建议用 3.13.x）。
- **Node.js 22+**（打包进 exe 的那份 Node 就是 22.22.2）。
- 能访问 npm 源（首次启动会从 npm 拉 `@deepseek-ai/dsh`）。

---

## 2. 准备

```bash
# 1) 克隆本仓库
git clone https://github.com/sv8vkwmfr7-create/agent.git
cd agent/src

# 2) 建虚拟环境并装依赖（pywebview 会顺带拉 pythonnet / clr_loader）
python -m venv .venv
.venv\Scripts\activate
pip install pywebview pywin32
pip install pyinstaller
```

`src/` 目录结构（构建前）：

```
src/
├─ dsh_desktop.py
├─ dsh-quit.py
├─ create-shortcut.py
├─ assets/
│  └─ deepseek-whale.ico
└─ DeepSeekHarness.spec   # 仓库里也提供了，可直接用
```

---

## 3. PyInstaller 打包

`dsh_desktop.py` 用到 **pywebview + pythonnet（.NET 互操作）**，普通 `--hidden-import` 不够，必须用 `collect_all` 把整个包的数据 / 二进制收进来，否则运行时报 `clr` / `bottle` / `proxy_tools` 缺失。仓库里已经给了 `DeepSeekHarness.spec`，直接：

```bash
pyinstaller DeepSeekHarness.spec
```

或者手动等价命令（与 spec 一致）：

```bash
pyinstaller ^
  --noconsole ^
  --icon assets/deepseek-whale.ico ^
  --add-data "assets;assets" ^
  --collect-all webview ^
  --collect-all pythonnet ^
  --collect-all clr_loader ^
  --hidden-import clr ^
  --hidden-import bottle ^
  --hidden-import proxy_tools ^
  --name DeepSeekHarness ^
  dsh_desktop.py
```

几个关键点（踩过的坑）：

| 要点 | 说明 |
| --- | --- |
| `--noconsole` | 否则启动时弹出一个黑框（终端窗口）。 |
| `--icon` | 只在 exe 里嵌图标。**任务栏 / Alt-Tab / 右键菜单用的是进程图标**，所以必须打包成 exe 才能真正显示蓝鲸，光用 `.py` 跑显示的是 Python 小蛇。 |
| `--collect-all webview/pythonnet/clr_loader` | 这三个包都有动态加载的二进制和数据文件，漏了就会 import 报缺模块。 |
| icon 不能在 `create_window` 里传 | pywebview 的 `icon` 参数是传给 `webview.start()` 的，不是 `create_window()`，传错会 TypeError 启动失败。 |

---

## 4. 把 Node 运行时一起打包（做成「解压即用」）

预编译包之所以「零安装」，是因为把一份 Node 运行时塞进了 `DeepSeekHarness/` 目录：

1. 下载 **Node.js Windows 64-bit 二进制版**（不是安装版，是 `node-vXX.X.X-win-x64.zip`）。
2. 解压后把里面的 `node.exe`、`npx.cmd`、`npm.cmd` 以及 `node_modules/` 整个复制到 `dist/DeepSeekHarness/node/`。
3. `dsh_desktop.py` 启动时会优先用同目录下的 `node/npx.cmd`；找不到才回退到系统 PATH 的 `npx`。

这样别人下载解压后，不需要装 Node 也能跑。

---

## 5. 打包成发布 zip

```bash
cd dist
# 把 DeepSeekHarness/ 整个目录压缩
powershell -Command "Compress-Archive -Path DeepSeekHarness -DestinationPath DeepSeekHarness-win64.zip"
```

然后去 GitHub 仓库 **Releases → Draft a new release**，把 `DeepSeekHarness-win64.zip` 作为附件上传即可。

---

## 6. 创建带热键的桌面快捷方式（可选）

想要全局快捷键 `Ctrl + Alt + D`：

- **手动**：右键 `DeepSeekHarness.exe` → 发送到 → 桌面快捷方式；再右键该快捷方式 → 属性 → 快捷键 → 按 `Ctrl + Alt + D`。
- **脚本**：`python create-shortcut.py`（需要本机有 `pywin32`，用 IShellLink 写 `.lnk` 的热键字段；PowerShell 的 WScript.Shell 在某些安全策略下会被拦）。

---

## 7. 创建桌面快捷方式脚本原理

`create-shortcut.py` 用的是 `pywin32` 的 `IShellLink`：

```python
import pythoncom
from win32com.shell import shell, shellcon

shortcut = pythoncom.CoCreateInstance(
    shell.CLSID_ShellLink, None,
    pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
shortcut.SetPath(r"DeepSeekHarness.exe")
# 热键 = (修饰键 << 8) | 虚拟键码
# Ctrl(0x02) + Alt(0x04) << 8 | 'D'(0x44) = 0x0644
shortcut.SetHotkey(0x0644)
persist = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
persist.Save(r"DeepSeek Harness.lnk", 0)
```
