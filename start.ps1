<#
.SYNOPSIS
  RRviewerX 一键启动脚本（本地 / Docker）。

.PARAMETER Mode
  local（默认）或 docker。

.PARAMETER BackendPort
  后端端口，默认 8000。

.PARAMETER FrontendPort
  前端端口，默认 8080。

.PARAMETER Workers
    Uvicorn worker 数。0 = 自动按环境选择；生产环境自动 2-4 个，开发环境 1 个。

.PARAMETER NoBrowser
  启用时不自动打开浏览器。

.PARAMETER SkipDeps
  跳过 pip install（加速重启）。

.EXAMPLE
  ./start.ps1
  ./start.ps1 -Mode docker
  ./start.ps1 -BackendPort 8001 -FrontendPort 9090 -Workers 2 -SkipDeps
#>

[CmdletBinding()]
param(
    [ValidateSet('local', 'docker')]
    [string]$Mode = 'local',

    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080,

    [ValidateRange(0, 32)]
    [int]$Workers = 0,

    [switch]$NoBrowser,
    [switch]$SkipDeps
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ── Pretty output helpers ───────────────────────────────────────────
function Write-Step  ([string]$m) { Write-Host "  > $m" -ForegroundColor Cyan }
function Write-OK    ([string]$m) { Write-Host "  + $m" -ForegroundColor Green }
function Write-Warn  ([string]$m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Write-Err   ([string]$m) { Write-Host "  x $m" -ForegroundColor Red }

function Write-Banner {
    Write-Host ''
    Write-Host '  ========================================' -ForegroundColor DarkCyan
    Write-Host '         RRviewerX  Dev  Launcher         ' -ForegroundColor DarkCyan
    Write-Host '  ========================================' -ForegroundColor DarkCyan
    Write-Host ''
}

# ── Utility functions ───────────────────────────────────────────────
function Test-Cmd ([string]$Name) {
    [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-EnvFileValue ([string]$Key) {
    $envFile = 'backend/.env'
    if (-not (Test-Path $envFile)) {
        return $null
    }

    $pattern = '^\s*' + [regex]::Escape($Key) + '=(.*)$'
    $line = Get-Content $envFile | Where-Object { $_ -match $pattern } | Select-Object -Last 1
    if (-not $line) {
        return $null
    }

    if ($line -match $pattern) {
        $value = $Matches[1].Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        return $value
    }

    return $null
}

function Get-AppEnv {
    $appEnv = $env:APP_ENV
    if ([string]::IsNullOrWhiteSpace($appEnv)) {
        $appEnv = Get-EnvFileValue 'APP_ENV'
    }
    if ([string]::IsNullOrWhiteSpace($appEnv)) {
        $appEnv = 'dev'
    }
    return $appEnv.ToLowerInvariant()
}

function Resolve-BackendWorkers ([int]$RequestedWorkers) {
    if ($RequestedWorkers -gt 0) {
        return $RequestedWorkers
    }

    $appEnv = Get-AppEnv
    if ($appEnv -in @('prod', 'production')) {
        $cpuCount = [Environment]::ProcessorCount
        if ($cpuCount -lt 2) { return 2 }
        if ($cpuCount -gt 4) { return 4 }
        return $cpuCount
    }

    return 1
}

function Test-PortBusy ([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        return ($null -ne $conn -and $conn.Count -gt 0)
    } catch { return $false }
}

function Assert-PortFree ([int]$Port, [string]$Label) {
    if (Test-PortBusy $Port) {
        Write-Err "Port $Port ($Label) is already in use."
        Write-Err "Run: Get-Process -Id (Get-NetTCPConnection -LocalPort $Port).OwningProcess"
        throw "Port $Port occupied"
    }
}

function Find-Python {
    # Try real interpreters first; 'python3' on Windows is often the Store stub
    foreach ($cmd in 'python', 'py') {
        if (Test-Cmd $cmd) {
            try {
                $ver = & $cmd --version 2>&1
                if ($ver -match 'Python 3') { return $cmd }
            } catch { }
        }
    }
    throw 'Python 3 not found. Install Python 3.10+ and ensure it is on PATH.'
}

# ── Virtual-env management ──────────────────────────────────────────
function Ensure-Venv {
    if (Test-Path '.venv/Scripts/python.exe') {
        Write-OK 'Virtual environment found'
        return
    }
    Write-Step 'Creating virtual environment (.venv) ...'
    $py = Find-Python
    if ($py -eq 'py') { & py -3 -m venv .venv }
    else               { & $py -m venv .venv    }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        throw 'Failed to create .venv - check your Python installation.'
    }
    Write-OK 'Virtual environment created'
}

function Install-Deps {
    $req = 'backend/requirements.txt'
    if (-not (Test-Path $req)) {
        Write-Warn "$req not found - skipping"
        return
    }
    Write-Step 'Installing backend dependencies ...'
    & .venv/Scripts/python.exe -m pip install --quiet --upgrade pip
    & .venv/Scripts/python.exe -m pip install --quiet -r $req
    Write-OK 'Dependencies installed'
}

# ── Service launchers ───────────────────────────────────────────────
function Start-Backend ([int]$Port, [int]$FEPort, [int]$W) {
    Assert-PortFree $Port 'backend'

    # Build ALLOWED_ORIGINS for CORS
    $origins = @(
        "http://localhost:$FEPort",
        "http://127.0.0.1:$FEPort",
        'http://localhost:5173',
        'http://localhost:3000'
    )
    try {
        $lanIPs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notmatch '^(169\.254\.|127\.)' } |
            Select-Object -ExpandProperty IPAddress
        foreach ($ip in $lanIPs) { $origins += "http://${ip}:$FEPort" }
    } catch { }
    $env:ALLOWED_ORIGINS = $origins -join ','

    $appEnv = Get-AppEnv
    $effectiveWorkers = Resolve-BackendWorkers $W
    $pyExe = Resolve-Path '.venv/Scripts/python.exe'
    $uvi   = @('-m', 'uvicorn', 'app.main:app',
               '--host', '0.0.0.0', '--port', "$Port",
               '--app-dir', 'backend', '--workers', "$effectiveWorkers")

    Write-Step "Starting backend -> http://localhost:$Port (workers=$effectiveWorkers, env=$appEnv)"
    Start-Process -FilePath $pyExe -ArgumentList $uvi -WorkingDirectory $PWD -WindowStyle Normal
    Write-OK "Backend PID launched (port $Port)"
}

function Start-Frontend ([int]$Port) {
    Assert-PortFree $Port 'frontend'
    $pagesDir = 'frontend/src/pages'
    if (-not (Test-Path $pagesDir)) { throw "Frontend dir missing: $pagesDir" }

    # Copy logo if available
    $logo = 'logo.png'
    $dst  = "$pagesDir/assets/logo.png"
    if ((Test-Path $logo) -and (-not (Test-Path $dst) -or
        (Get-Item $logo).LastWriteTime -gt (Get-Item $dst).LastWriteTime)) {
        Copy-Item $logo $dst -Force
    }

    $pyExe = Resolve-Path '.venv/Scripts/python.exe'
    Write-Step "Starting frontend -> http://localhost:$Port"
    Start-Process -FilePath $pyExe `
        -ArgumentList '-m', 'http.server', "$Port", '-d', $pagesDir `
        -WorkingDirectory $PWD -WindowStyle Normal
    Write-OK "Frontend PID launched (port $Port)"
}

# ── Docker mode ─────────────────────────────────────────────────────
function Start-Docker ([int]$WorkerCount) {
    if (-not (Test-Cmd 'docker')) {
        throw 'Docker is not installed or not on PATH.'
    }

    $previousWorkers = $null
    $hadWorkers = Test-Path Env:UVICORN_WORKERS
    if ($hadWorkers) {
        $previousWorkers = $env:UVICORN_WORKERS
    }

    try {
        if ($WorkerCount -gt 0) {
            $env:UVICORN_WORKERS = "$WorkerCount"
        } elseif (-not $hadWorkers) {
            $env:UVICORN_WORKERS = '2'
        }

        Write-Step "Building & starting containers (docker compose, backend workers=$($env:UVICORN_WORKERS)) ..."
        docker compose up --build -d
        Write-OK 'Docker services started'
    } finally {
        if ($hadWorkers) {
            $env:UVICORN_WORKERS = $previousWorkers
        } else {
            Remove-Item Env:UVICORN_WORKERS -ErrorAction SilentlyContinue
        }
    }
}

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
Write-Banner

switch ($Mode) {
    'local' {
        Ensure-Venv
        if (-not $SkipDeps) { Install-Deps } else { Write-Warn 'Skipping deps (-SkipDeps)' }
        Start-Backend  -Port $BackendPort -FEPort $FrontendPort -W $Workers
        Start-Frontend -Port $FrontendPort

        Write-Host ''
        Write-Host "  -----------------------------------------" -ForegroundColor DarkGreen
        Write-Host "    Frontend : http://localhost:$FrontendPort" -ForegroundColor DarkGreen
        Write-Host "    Backend  : http://localhost:$BackendPort" -ForegroundColor DarkGreen
        Write-Host "  -----------------------------------------" -ForegroundColor DarkGreen
        Write-Host ''

        if (-not $NoBrowser) {
            Start-Sleep -Milliseconds 800
            try { Start-Process "http://localhost:$FrontendPort/index.html" } catch { }
        }
    }
    'docker' {
        Start-Docker -WorkerCount $Workers
        Write-Host ''
        Write-OK "Frontend -> http://localhost:$FrontendPort   Backend -> http://localhost:$BackendPort"
        Write-Host ''
    }
}
