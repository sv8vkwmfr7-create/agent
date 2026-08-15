# 发布到 GitHub

本仓库内容已经 `git init` + `git commit` 完成，位于 `C:\Users\ASYS\dsh-desktop\agent\`。
由于打包环境无法直连 GitHub，请在本机（有网络）执行以下步骤完成上传。

---

## 方式 A：一键脚本（推荐）

**前置条件**
- 本机已安装 Git。
- 一个具有 `repo` 权限的 GitHub Personal Access Token（PAT，classic）：
  GitHub → 右上角头像 → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾选 **`repo`**（全部子项），生成后复制。

**执行**
在本机打开 PowerShell，进入 `agent` 目录，运行：

```powershell
cd C:\Users\ASYS\dsh-desktop\agent
.\publish.ps1 -Token ghp_你的token
```

脚本会自动完成：
1. 创建仓库 `sv8vkwmfr7-create/agent`（若已存在则跳过）；
2. 推送全部代码（`master` 分支）；
3. 创建 Release `v1.0.0`；
4. 上传 `DeepSeekHarness-win64.zip` 作为下载附件。

> Token 只在命令里用一次，不会写入任何文件。用完可在 GitHub 撤销该 token。

---

## 方式 B：手动（不用脚本）

1. 在 GitHub 新建**空**仓库 `sv8vkwmfr7-create/agent`（不要勾选 Initialize with README / .gitignore，保持完全为空）。
2. 本机进入 `agent` 目录推送：

   ```bash
   cd C:\Users\ASYS\dsh-desktop\agent
   git remote add origin https://<TOKEN>@github.com/sv8vkwmfr7-create/agent.git
   git branch -M master
   git push -u origin master
   ```

3. 在仓库页面 → **Releases** → **Draft a new release**：
   - Tag: `v1.0.0`
   - Title: `DeepSeek Harness 桌面版 v1.0.0`
   - 把 `C:\Users\ASYS\dsh-desktop\DeepSeekHarness-win64.zip` 拖到附件区 → **Publish release**。

---

## 关于预编译包 `DeepSeekHarness-win64.zip`

- 大小约 **50 MB**，里面已经包含 Node.js 运行时，所以别人「下载 → 解压 → 双击 exe」即可用，零安装。
- 它**不在 git 仓库内**（仓库只放源码和小体积资源），而是作为 GitHub Release 的附件提供，这样下载最方便、仓库也干净。
- 路径：`C:\Users\ASYS\dsh-desktop\DeepSeekHarness-win64.zip`。

---

## 仓库里有什么

```
agent/
├─ README.md               面向使用者的下载 / 使用教程
├─ PUBLISH.md              本文：如何发布到 GitHub
├─ LICENSE                 MIT
├─ publish.ps1             一键发布脚本（需要 PAT）
├─ .gitignore
└─ src/
   ├─ dsh_desktop.py       桌面启动器源码（Python + pywebview + Edge WebView2）
   ├─ DeepSeekHarness.spec PyInstaller 打包配置
   ├─ assets/deepseek-whale.ico  DeepSeek 官方蓝鲸图标
   ├─ dsh-quit.py          退出服务的小助手
   ├─ create-shortcut.py   生成带 Ctrl+Alt+D 热键的桌面快捷方式
   └─ build.md             从源码构建说明
```

发布完成后，把仓库地址 `https://github.com/sv8vkwmfr7-create/agent` 发给别人即可。
