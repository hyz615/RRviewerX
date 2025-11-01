<#
.SYNOPSIS
启动本地或 Docker 开发环境（后端 FastAPI + 前端静态页）。

.DESCRIPTION
默认模式会：
- 创建/激活 Python 虚拟环境 .venv
- 安装后端依赖（backend/requirements.txt）
- 启动后端 (Uvicorn) 与前端 (python -m http.server)

.PARAMETER Mode
local（默认）：本地启动；docker：使用 docker compose。

.PARAMETER BackendPort
后端端口，默认 8000。

.PARAMETER FrontendPort
前端端口，默认 8080。

.PARAMETER NoBrowser
启用后不自动打开浏览器。

.EXAMPLE
./start.ps1

.EXAMPLE
./start.ps1 -Mode local -BackendPort 8001 -FrontendPort 9090

.EXAMPLE
./start.ps1 -Mode docker
#>

[CmdletBinding()]
Param(
    [ValidateSet("local","docker")]
    [string]$Mode = "local",

    [int]$BackendPort = 8000,
    [int]$FrontendPort = 8080,

    # 并发工作进程数（Uvicorn workers）。0 表示不指定，由 Uvicorn 默认决定（通常为 1）。
    [int]$Workers = 0,

    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Info([string]$msg) { Write-Host "[info] $msg" -ForegroundColor Yellow }
function Write-Step([string]$msg) { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-Run([string]$msg)  { Write-Host "[run] $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host "[warn] $msg" -ForegroundColor DarkYellow }
function Write-Err2([string]$msg) { Write-Host "[error] $msg" -ForegroundColor Red }

function Show-Usage {
    Write-Host "Usage: ./start.ps1 [-Mode local|docker] [-BackendPort <int>] [-FrontendPort <int>] [-NoBrowser]" -ForegroundColor Yellow
}

function Test-CommandExists([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-PortInUse([int]$Port) {
    try {
        $lines = (netstat -ano | Select-String ":$Port\s").ToString()
        return -not [string]::IsNullOrEmpty($lines)
    } catch { return $false }
}

function Ensure-Venv {
    if (-not (Test-Path ".venv")) {
        Write-Step "Creating venv at .venv"
        try {
            if (Test-CommandExists "py") { py -3.11 -m venv .venv }
            elseif (Test-CommandExists "python") { python -m venv .venv }
            else { throw "Python is not installed or not in PATH." }
        } catch {
            throw "Failed to create virtual environment: $($_.Exception.Message)"
        }
    }
}

function Activate-Venv {
    $activate = Join-Path ".venv" "Scripts/Activate.ps1"
    if (-not (Test-Path $activate)) {
        throw "Virtual environment activation script not found: $activate"
    }
    . $activate
}

function Install-Backend-Deps {
    Write-Step "Installing backend dependencies"
    if (-not (Test-Path "backend/requirements.txt")) {
        Write-Warn2 "backend/requirements.txt not found, skipping dependency install."
        return
    }
    pip install -U pip *> $null
    pip install -r "backend/requirements.txt"
}

function Start-Backend([int]$Port,[int]$FrontendPortParam,[int]$WorkersParam) {
    # Build allowed origins including localhost, loopback and LAN IP
    try {
        $ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^169\.254\.' -and $_.IPAddress -ne '127.0.0.1' } | Select-Object -ExpandProperty IPAddress)
    } catch { $ips = @() }
    if (-not $ips) { $ips = @() }
    $origins = @("http://localhost:$FrontendPortParam","http://127.0.0.1:$FrontendPortParam","http://localhost:5173","http://localhost:3000")
    foreach ($ip in $ips) { $origins += "http://$($ip):$FrontendPortParam" }
    $env:ALLOWED_ORIGINS = ($origins -join ',')
    $pythonExe = Join-Path ".venv" "Scripts/python.exe"
    if (-not (Test-Path $pythonExe)) { throw "Python executable not found in .venv: $pythonExe" }
    if (Test-PortInUse $Port) { Write-Warn2 "Port $Port seems in use; backend may fail to bind." }
    Write-Run "Starting backend at http://localhost:$Port"
    $args = @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","$Port","--app-dir","backend")
    if ($WorkersParam -gt 0) {
        $args += @("--workers","$WorkersParam")
    }
    Start-Process -FilePath (Resolve-Path $pythonExe) `
        -ArgumentList $args `
        -WorkingDirectory (Get-Location) `
        -WindowStyle Normal | Out-Null
}

function Start-Frontend([int]$Port) {
    if (-not (Test-Path "frontend/src/pages")) { throw "Frontend directory not found: frontend/src/pages" }
    $pythonExe = Join-Path ".venv" "Scripts/python.exe"
    if (-not (Test-Path $pythonExe)) { throw "Python executable not found in .venv: $pythonExe" }
    # Ensure logo asset available under served root (frontend/src/pages/assets/logo.png)
    try {
        $dstDir = Join-Path "frontend/src/pages" "assets"
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        $srcLogo = Join-Path (Get-Location) "logo.png"
        $dstLogo = Join-Path $dstDir "logo.png"
        if (Test-Path $srcLogo) {
            Copy-Item -Path $srcLogo -Destination $dstLogo -Force
        } elseif (-not (Test-Path $dstLogo)) {
            Write-Warn2 "logo.png not found in repository root; top-left logo image may be missing."
        }
    } catch { Write-Warn2 "Failed to prepare logo asset: $($_.Exception.Message)" }
    if (Test-PortInUse $Port) { Write-Warn2 "Port $Port seems in use; frontend may fail to bind." }
    Write-Run "Serving frontend at http://localhost:$Port"
    Start-Process -FilePath (Resolve-Path $pythonExe) `
        -ArgumentList "-m","http.server","$Port","-d","frontend/src/pages" `
        -WorkingDirectory (Get-Location) `
        -WindowStyle Normal | Out-Null
}

switch ($Mode) {
    "local" {
        Ensure-Venv
        Activate-Venv
        Install-Backend-Deps
    Start-Backend -Port $BackendPort -FrontendPortParam $FrontendPort -WorkersParam $Workers
        Start-Frontend -Port $FrontendPort
        Start-Sleep -Seconds 1
        Write-Info "Open frontend: http://localhost:$FrontendPort/index.html"
        Write-Info "Backend API: http://localhost:$BackendPort"
        if (-not $NoBrowser) {
            try { Start-Process "http://localhost:$FrontendPort/index.html" | Out-Null } catch {}
        }
    }
    "docker" {
        Write-Step "Building and starting services (frontend:$FrontendPort, backend:$BackendPort)"
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            docker compose up --build
        } else {
            throw "Docker is not installed or not in PATH."
        }
    }
}
