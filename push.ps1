<#
.SYNOPSIS
  Git add / commit / push 快捷脚本。

.PARAMETER Message
  提交信息。省略时自动生成时间戳消息。

.PARAMETER Branch
  目标分支，默认 main。

.PARAMETER Force
  使用 --force 推送（慎用）。

.EXAMPLE
  ./push.ps1 "feat: add dark mode"
  ./push.ps1 -Branch dev
  ./push.ps1                       # 自动消息 "update 2026-03-21 14:30"
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Message,

    [string]$Branch = 'main',

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step ([string]$m) { Write-Host "  > $m" -ForegroundColor Cyan }
function Write-OK   ([string]$m) { Write-Host "  + $m" -ForegroundColor Green }
function Write-Err  ([string]$m) { Write-Host "  x $m" -ForegroundColor Red }

# ── Pre-flight checks ──
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git is not installed or not on PATH.'
}
if (-not (Test-Path '.git')) {
    throw 'Not a git repository. Run from the project root.'
}

# ── Auto-generate commit message if not provided ──
if ([string]::IsNullOrWhiteSpace($Message)) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $Message = "update $ts"
}

# ── Show status ──
Write-Host ''
Write-Host '  ========================================' -ForegroundColor DarkCyan
Write-Host '         RRviewerX  Git  Push             ' -ForegroundColor DarkCyan
Write-Host '  ========================================' -ForegroundColor DarkCyan
Write-Host ''

$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-OK 'Working tree clean - nothing to commit.'
    return
}

Write-Step "Changed files:"
git status --short | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
Write-Host ''

# ── Stage, Commit, Push ──
Write-Step 'Staging all changes ...'
git add -A

Write-Step "Committing: $Message"
git commit -m $Message

$pushArgs = @('push', 'origin', $Branch)
if ($Force) {
    Write-Err  'WARNING: Force push enabled!'
    $pushArgs += '--force'
}

Write-Step "Pushing to origin/$Branch ..."
git @pushArgs

Write-Host ''
Write-OK "Pushed to origin/$Branch"
Write-Host ''
