<#
.SYNOPSIS
    Install the XY-MD02 WebApp to run in the background at Windows startup, also without login.

.DESCRIPTION
    - Creates a Python virtual environment and installs the dependencies
    - Registers the scheduled task "XY-MD02 WebApp": runs at startup as SYSTEM (no login needed)
      and restarts the app when it stops (run-app.cmd)
    - Opens the web port in the Windows firewall
    Run in PowerShell as Administrator, in the app folder:
        powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-service.ps1
    Run again to update after changing the app or the port.

.PARAMETER Port
    Web port to open in the firewall (default 8050, change it if you changed the port in Settings).
#>
param(
    [int]$Port = 8050
)

$ErrorActionPreference = 'Stop'
$TaskName = 'XY-MD02 WebApp'
$FirewallRule = 'XY-MD02 WebApp'
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Runner = Join-Path $PSScriptRoot 'run-app.cmd'
$VenvPython = Join-Path $AppDir '.venv\Scripts\python.exe'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'Run this script as Administrator (right-click PowerShell > Run as administrator).'
    exit 1
}

Write-Host "-> App folder: $AppDir"

# Python 3.10+ (py launcher from python.org, otherwise python on PATH)
$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $Python = @('py', '-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = @('python') }
if (-not $Python) {
    Write-Error 'Python not found. Install Python 3.10 or newer from https://www.python.org/downloads/ (tick "Add python.exe to PATH").'
    exit 1
}
$PyExe = $Python[0]
$PyArgs = @($Python | Select-Object -Skip 1)
& $PyExe @PyArgs -c 'import sys; sys.exit(sys.version_info < (3, 10))'
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Python 3.10 or newer is required.'
    exit 1
}

# Stop a running instance before updating
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$AppDir\app.py") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# Virtual environment and dependencies
if (-not (Test-Path $VenvPython)) {
    Write-Host '-> Creating virtual environment'
    & $PyExe @PyArgs -m venv (Join-Path $AppDir '.venv')
    if ($LASTEXITCODE -ne 0) { Write-Error 'Creating the virtual environment failed.'; exit 1 }
}
Write-Host '-> Installing dependencies'
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $AppDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Error 'Installing dependencies failed.'; exit 1 }

# Scheduled task: at startup, as SYSTEM, no time limit, restart if the task itself fails
Write-Host "-> Registering scheduled task '$TaskName'"
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$Runner`"" -WorkingDirectory $AppDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskPrincipal `
    -Settings $taskSettings -Description 'XY-MD02 temperature and humidity WebApp' -Force | Out-Null

# Firewall: allow the web port
Write-Host "-> Opening TCP port $Port in the Windows firewall"
Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5
Write-Host ''
Write-Host 'Installed. The app starts automatically at Windows startup, also without login.'
Write-Host "  Open:      http://localhost:$Port  (from other computers: http://<this-pc-ip>:$Port)"
Write-Host "  Logs:      $AppDir\logs\app.log"
Write-Host "  Status:    Get-ScheduledTask -TaskName '$TaskName' | Select-Object State"
Write-Host "  Uninstall: powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\uninstall-service.ps1`""
