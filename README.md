# DeepSeek Harness 桌面版（Windows）

把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的网页版（`npx @deepseek-ai/dsh web`，默认跑在 `http://127.0.0.1:3080`）**封装成一个原生 Windows 桌面程序**，并绑定一个全局快捷键，不用每次都开命令行、开浏览器。

> 窗口用系统自带的 **Edge WebView2** 渲染（和 Edge 同内核，不是 Chromium 套壳），所以桌面 app 本身只有几 MB；Node 运行时已经一起打包，**解压即用，零安装**。

[![最新版本](https://img.shields.io/github/v/release/sv8vkwmfr7-create/agent?label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC&color=2294F2)](https://github.com/sv8vkwmfr7-create/agent/releases)

<a href="https://github.com/sv8vkwmfr7-create/agent/releases">
  <img src="https://img.shields.io/badge/%E4%B8%8B%E8%BD%BD%E6%A1%8C%E9%9D%A2%E7%89%88-2294F2?style=for-the-badge" alt="下载桌面版"/>
</a>

---

## ✨ 特性

- 🐳 **原生桌面窗口**：蓝鲸图标，任务栏 / 右键菜单 / Alt-Tab 都是 DeepSeek 蓝鲸，不再是 Python 小蛇。
- ⌨️ **全局快捷键 `Ctrl + Alt + D`**：随时一键唤起 / 聚焦窗口（单实例，重复按不会开一堆窗口）。
- 📦 **自带 Node 运行时**：下载包里已经包含 Node.js，不需要你先装 Node。
- 📡 **离线启动（v1.0.1）**：`@deepseek-ai/dsh` 依赖已随包分发，首次启动**无需联网**，也不依赖对方电脑的 Node/npm 版本。
- 🚫 **无终端窗口（v1.0.1）**：全程静默启动，不再闪现命令行窗口。
- ⚡ **秒开（v1.0.1）**：服务就绪后热启动秒开；本地模式跳过 npm 缓存扫描。
- 🪶 **轻量**：不依赖 Electron，借助系统 WebView2。
- 🔑 **支持 API Key / 环境变量**：通过 `.env` 文件或系统环境变量注入（如 `DEEPSEEK_API_KEY`）。

---

## 📥 下载（两种方式）

### 方式一：下载预编译包（最方便，推荐）

1. 打开本仓库的 **Releases** 页面（右侧或仓库顶部 `Releases`）。
2. 下载 **`DeepSeekHarness-win64.zip`**。
3. 解压到任意目录（例如 `D:\Apps\DeepSeekHarness\`）。
4. 双击里面的 **`DeepSeekHarness.exe`** 即可启动。

> ✅ 包内已含 Node.js 与 dsh 应用本体，无需安装任何东西、无需联网。解压即用。

### 方式二：从源码自己构建（适合想改代码的开发者）

见仓库 `src/` 目录与 `src/build.md`。需要本机有 Python 3.13 和 Node.js 22+。

---

## 🚀 使用教程

### 1. 启动

- **方式 A（双击）**：直接双击 `DeepSeekHarness.exe`。
- **方式 B（快捷键）**：在桌面建一个指向 `DeepSeekHarness.exe` 的快捷方式，并给它设快捷键 `Ctrl + Alt + D`：
  - 右键 `DeepSeekHarness.exe` → **发送到 → 桌面快捷方式**。
  - 右键桌面那个快捷方式 → **属性** → **快捷方式** → **快捷键** → 按下 `Ctrl + Alt + D` → 确定。
  - 之后任何时候按 `Ctrl + Alt + D` 就能唤起窗口。
  - 嫌麻烦也可以用仓库里的 `create-shortcut.py`（需要本机有 Python + `pywin32`）自动建好带热键的快捷方式。

### 2. 配置 API Key（如需要）

DeepSeek Harness 可能需要 API Key 才能用。任选一种方式：

- **方法一（推荐）**：在 `DeepSeekHarness.exe` 所在目录新建 `.env` 文件：
  ```ini
  DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
  ```
  启动器会自动把它注入到 dsh 服务进程。
- **方法二**：在 Windows「系统属性 → 高级 → 环境变量」里添加用户级 `DEEPSEEK_API_KEY`。

### 3. 关闭与退出

- 关闭窗口即退出桌面版；`dsh web` 服务进程会保留，下次启动更快。
- 想彻底退出服务：仓库 `src/dsh-quit.py` 可发送退出信号（需本机 Python）。

---

## 🔧 排错

启动器日志：`DeepSeekHarness/dsh-desktop.log`
dsh web 服务日志：`DeepSeekHarness/dsh-server.log`

常见问题：

| 现象 | 排查 |
| --- | --- |
| 窗口空白 / 打不开 | 先看 `dsh-server.log`；v1.0.1 起已离线内置 dsh，若日志出现 npm 报错，可尝试删除安装目录重解压。 |
| 提示找不到 Node | 预编译包已自带 Node；若你是用源码构建的版本，请确保本机装有 Node.js 22+ 并在 PATH 中。 |
| 任务栏图标不是蓝鲸 | 确保你是直接运行 `DeepSeekHarness.exe`（图标已内嵌），而不是 `.py` 脚本。 |
| 快捷键没反应 | 右键快捷方式 → 属性 → 快捷键重新按一下；或注销重登一次。确认 `.lnk` 在桌面 / 开始菜单。 |

---

## 📋 更新日志

### v1.0.1（2026-08-17）

- 📡 **离线启动**：dsh 应用本体随包分发，不再依赖系统 Node/npm 版本与网络
- 🚫 **修复终端窗口闪现**：所有控制台子进程无窗口化执行
- ⚡ **启动提速**：本地模式跳过 npm 缓存校验（每次省约 10s）；窗口关闭后保留服务，再次打开秒开
- 🐛 保留 v1.0.0 全部健壮性改进（缓存损坏自愈、进度可见、错误可见、WebView2 检测）

### v1.0.0（2026-08-15）

- 首个正式版：原生桌面窗口封装 + 全局快捷键 + 单实例 + 自带 Node 运行时

---

## 🗂 仓库结构

```
agent/
├─ README.md                     本说明
├─ LICENSE                       MIT
├─ src/
│  ├─ dsh_desktop.py             桌面启动器源码（Python + pywebview）
│  ├─ assets/deepseek-whale.ico  DeepSeek 官方蓝鲸图标
│  ├─ dsh-quit.py               退出服务的小助手
│  ├─ create-shortcut.py         生成带 Ctrl+Alt+D 热键的桌面快捷方式
│  └─ build.md                   从源码构建说明
└─ (Releases) DeepSeekHarness-win64.zip   预编译桌面版（含 Node）
```

---

## 📜 许可证

- 本桌面包装器以 **MIT** 许可证发布。
- DeepSeek Harness 本身的许可证见其[官方仓库](https://github.com/deepseek-ai/deepseek-harness)（MIT）。
- DeepSeek 蓝鲸图标为其品牌资产，仅用于个人桌面使用。

---

## ❓ 它是怎么工作的（简述）

`dsh_desktop.py` 启动时：

1. 通过本地控制端口实现**单实例**（重复启动只聚焦已有窗口）。
2. 若 `http://127.0.0.1:3080` 尚未运行，则用自带的 Node 执行 `npx -y @deepseek-ai/dsh web` 拉起服务。
3. 等到服务就绪后，用 **pywebview（Edge WebView2）** 打开一个原生窗口加载该地址。
4. 蓝鲸图标内嵌在 exe 资源里，所以任务栏 / 菜单都显示鲸鱼。
