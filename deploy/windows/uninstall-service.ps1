<#
.SYNOPSIS
    Stop and remove the XY-MD02 WebApp scheduled task and firewall rule. Data is kept.
    Run in PowerShell as Administrator:
        powershell -ExecutionPolicy Bypass -File .\deploy\windows\uninstall-service.ps1
#>
$ErrorActionPreference = 'Stop'
$TaskName = 'XY-MD02 WebApp'
$FirewallRule = 'XY-MD02 WebApp'
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'Run this script as Administrator.'
    exit 1
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
# The task runs cmd.exe -> python.exe; stop the app process as well
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$AppDir\app.py") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "Removed '$TaskName'. The app folder and its data were not touched."
