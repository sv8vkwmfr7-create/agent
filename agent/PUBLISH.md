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
3. 创建 Release `v1.0.3`；
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
   - Tag: `v1.0.3`
   - Title: `DeepSeek Harness 桌面版 v1.0.3`
   - 把 `C:\Users\ASYS\dsh-desktop\DeepSeekHarness-win64.zip` 拖到附件区 → **Publish release**。

---

## 方式 C：免 token 发布（推荐给不想管 token 的人）

适合你已经在 GitHub 网页登录过账号的情况。核心思路：用 **HTTPS 远程地址 + Git 凭据管理器**，第一次 push 时自动弹出 GitHub 登录网页，登录后就能推，**全程不用复制粘贴 token**。

### 一次性准备（你来做）
1. 在 GitHub 网页新建**空**仓库 `sv8vkwmfr7-create/agent`（不要勾 README / .gitignore，保持完全为空）。
2. 确认本机装了 Git for Windows（自带 Git Credential Manager）。没装去 https://git-scm.com 下一个。

### 一条命令推代码
在本机终端（PowerShell 或 Git Bash 都行）执行：

```bash
cd C:\Users\ASYS\dsh-desktop\agent
git remote add origin https://github.com/sv8vkwmfr7-create/agent.git
git push -u origin master
```

首次 push 会弹浏览器让你登录 GitHub，授权后代码就上去了。之后再次 push 不用再登录。

> 偏好 SSH 的话，把上面 `git remote add` 那行换成：
> `git remote add origin git@github.com:sv8vkwmfr7-create/agent.git`
> （需先在 GitHub 账号添加本机 SSH 公钥，一次性设置，之后永免登录）。

### 上传预编译包（手动，免 token）
进仓库 → **Releases** → **Draft a new release** → Tag 填 `v1.0.1` → 把
`C:\Users\ASYS\dsh-desktop\DeepSeekHarness-win64.zip` 拖进附件区 → **Publish release**。

---

## 关于预编译包 `DeepSeekHarness-win64.zip`

- 大小约 **134 MB**（v1.0.1 起内置 dsh 应用依赖），里面已经包含 Node.js 运行时与 dsh 本体，所以别人「下载 → 解压 → 双击 exe」即可用，零安装、零联网。
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
