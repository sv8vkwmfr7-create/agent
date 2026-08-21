DeepSeek Harness —— 桌面版启动器
====================================

把你平时用的 `npx @deepseek-ai/dsh web`（网页版，http://127.0.0.1:3080）
封装成了一个原生桌面窗口，并绑定全局快捷键。

【怎么用】
1. 在桌面找到「DeepSeek Harness」快捷方式。
2. 任何时候按  Ctrl + Alt + D  （全局热键）即可启动/聚焦桌面窗口。
   若服务已在运行，会直接复用；若窗口已开，会聚焦到已有窗口（单实例）。
3. 关闭窗口即退出桌面版；dsh web 服务进程会保留，下次启动更快。
   想彻底退出服务：双击运行 dsh-quit.py（或在命令行 python dsh-quit.py）。

【自动更新引擎】
启动时自动检查 dsh 引擎版本，发现新版本时弹窗提示一键更新。
更新只需 npm install，完成后自动重启，无需重新下载安装包。
也可跳过，不影响正常使用。

【配置 API Key 等环境变量】
- 把 .env.example 复制为 .env，填入你自己的变量（如 DEEPSEEK_API_KEY）。
  启动器会自动把它们注入到 dsh web 服务进程。
- 也可直接在 Windows「系统属性 → 高级 → 环境变量」里设置用户级变量。

【创建桌面快捷方式（Ctrl+Alt+D 热键）】
- 手动：右键 DeepSeekHarness.exe → 发送到 → 桌面快捷方式；
  再右键该快捷方式 → 属性 → 快捷方式 → 快捷键 → 按下 Ctrl+Alt+D → 确定。
- 自动：运行 agent/src/create-shortcut.py（需 Python + pywin32）。

【改端口 / 主机】
- 在 .env 里设置 DSH_WEB_PORT / DSH_WEB_HOST，或在 dsh_desktop.py 顶部修改。

【排错】
- 启动失败看 dsh-desktop.log；dsh web 服务日志在 dsh-server.log。
- 更新失败可手动在 app 目录执行 npm install，不影响正常使用。
- 需要 Edge WebView2 运行时（Win10/11 一般已自带）。如缺失请安装：
  https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/

文件清单：
  dsh_desktop.py   主程序（原生桌面窗口 + 单实例 + 热键聚焦 + 自动更新）
  dsh-quit.py      发送退出信号的助手
  .env.example     环境变量模板
  dsh-desktop.log  启动器日志
  dsh-server.log   dsh web 服务日志
