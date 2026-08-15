<#
.SYNOPSIS
    一键把本仓库发布到 GitHub：创建仓库（若不存在）→ 推送代码 → 创建 Release → 上传预编译包。

.DESCRIPTION
    在「有网络」的本机 PowerShell 里运行。需要 GitHub Personal Access Token（classic，勾选 repo 权限）。
    Token 仅用于本次操作，不会写入任何文件。

.EXAMPLE
    .\publish.ps1 -Token ghp_xxxxxxxxxxxx
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$RepoOwner = "sv8vkwmfr7-create",
    [string]$RepoName  = "agent",
    [string]$Branch    = "master",
    [string]$ZipPath   = "..\DeepSeekHarness-win64.zip",
    [string]$TagName   = "v1.0.0",
    [string]$ReleaseName = "DeepSeek Harness 桌面版 v1.0.0"
)

$ErrorActionPreference = "Stop"
$api     = "https://api.github.com"
$headers = @{
    Authorization = "Bearer $Token"
    Accept        = "application/vnd.github+json"
    "User-Agent"  = "dsh-publish-script"
}
$full = "$RepoOwner/$RepoName"

# 1) 确保仓库存在
$repoExists = $false
try {
    Invoke-RestMethod -Uri "$api/repos/$full" -Headers $headers -Method Get | Out-Null
    $repoExists = $true
    Write-Host "[1/4] 仓库已存在: $full"
} catch [System.Net.WebException] {
    $code = $_.Exception.Response.StatusCode
    if ($code -eq 404) {
        Write-Host "[1/4] 仓库不存在，正在创建 $full ..."
        $body = @{
            name        = $RepoName
            description = "DeepSeek Harness 桌面版（Windows）— 蓝鲸图标 + Ctrl+Alt+D 快捷键，自带 Node，解压即用"
            private     = $false
        } | ConvertTo-Json
        Invoke-RestMethod -Uri "$api/user/repos" -Headers $headers -Method Post -Body $body -ContentType "application/json" | Out-Null
        Write-Host "[1/4] 仓库已创建"
    } else {
        throw
    }
}

# 2) 推送代码
Set-Location $PSScriptRoot
$remote = "https://$Token@github.com/$full.git"
git remote remove origin 2>$null
git remote add origin $remote
git branch -M $Branch
Write-Host "[2/4] 推送分支 $Branch ..."
$push = git push -u origin $Branch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "推送失败（可能是远程已存在文件导致冲突）。如需覆盖，可手动执行：git push -u origin $Branch --force"
    Write-Warning ($push | Out-String)
    exit 1
}
Write-Host "[2/4] 推送完成"

# 3) 创建 Release
Write-Host "[3/4] 创建 Release $TagName ..."
$relBody = @{
    tag_name   = $TagName
    name       = $ReleaseName
    body       = "预编译桌面版，含 Node 运行时，解压即用。下载与使用见 README。热键 Ctrl+Alt+D，蓝鲸图标。"
    draft      = $false
    prerelease = $false
} | ConvertTo-Json
$rel = Invoke-RestMethod -Uri "$api/repos/$full/releases" -Headers $headers -Method Post -Body $relBody -ContentType "application/json"
Write-Host "[3/4] Release 已创建: $($rel.html_url)"

# 4) 上传附件
if (Test-Path $ZipPath) {
    $fn = Split-Path $ZipPath -Leaf
    $uploadUrl = $rel.upload_url -replace "\{\?.*\}", "?name=$([uri]::EscapeDataString($fn))"
    Write-Host "[4/4] 上传附件 $fn ($([math]::Round((Get-Item $ZipPath).Length/1MB, 1)) MB) ..."
    Invoke-RestMethod -Uri $uploadUrl -Headers $headers -Method Post -InFile $ZipPath -ContentType "application/zip" | Out-Null
    Write-Host "[4/4] 附件已上传"
} else {
    Write-Warning "[4/4] 未找到 $ZipPath —— 请手动到 Release 页面拖入 DeepSeekHarness-win64.zip"
}

Write-Host ""
Write-Host "✅ 完成！仓库地址: https://github.com/$full"
Write-Host "   下载页面:      https://github.com/$full/releases"
