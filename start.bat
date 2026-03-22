@echo off
REM ?? RRviewerX Quick Launcher (bat wrapper) ??
REM Delegates to start.ps1 with all arguments forwarded.
REM Usage:  start.bat
REM         start.bat -Mode docker
REM         start.bat -BackendPort 8001 -SkipDeps

where pwsh >nul 2>&1 && (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
    goto :eof
)

where powershell >nul 2>&1 && (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
    goto :eof
)

echo [ERROR] PowerShell not found. Install PowerShell 7+ or Windows PowerShell.
exit /b 1
