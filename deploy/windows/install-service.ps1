<#
.SYNOPSIS
    Install the XY-MD02 WebApp to run in the background at Windows startup, also without login.

.DESCRIPTION
    - Creates a Python virtual environment and installs the dependencies
    - Registers the scheduled task "XY-MD02 WebApp": runs at startup as LOCAL SERVICE (a limited
      built-in account, no login needed) and restarts the app when it stops (run-app.cmd)
    - Opens the web port in the Windows firewall for domain and private networks
    Run in PowerShell as Administrator, in the app folder:
        powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-service.ps1
    Run again to update after changing the app or the port.

.PARAMETER Port
    Web port to open in the firewall (default 8050, change it if you changed the port in Settings).

.PARAMETER AllowPublic
    Also open the port on networks marked as "Public" (not recommended).
#>
param(
    [int]$Port = 8050,
    [switch]$AllowPublic
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

# The task runs code from the app folder. Only administrators may be able to change it,
# otherwise a normal user could run commands as the service account.
$TrustedSids = @(
    'S-1-5-18',       # SYSTEM
    'S-1-5-32-544',   # Administrators
    'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'   # TrustedInstaller
)
# Only real write rights (Modify/FullControl also contain read bits, so do not test against those)
$WriteBits = [int64](2 -bor 4 -bor 16 -bor 64 -bor 256 -bor 65536 -bor 262144 -bor 524288)   # write/append/delete/ACL/owner
$GenericWriteBits = [int64](0x40000000 -bor 0x10000000)                                         # GENERIC_WRITE, GENERIC_ALL
foreach ($Path in @($AppDir, (Join-Path $AppDir 'app.py'), (Join-Path $AppDir 'deploy\windows\run-app.cmd'))) {
    if (-not (Test-Path $Path)) { continue }
    $Unsafe = (Get-Acl $Path).Access | Where-Object {
        $Ace = $_
        $Rights = [int64]$Ace.FileSystemRights
        $Sid = try { $Ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $Ace.IdentityReference.Value }
        $Ace.AccessControlType -eq 'Allow' -and
        -not ($Ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and
        (($Rights -band $WriteBits) -or ($Rights -band $GenericWriteBits)) -and
        $TrustedSids -notcontains $Sid
    }
    if ($Unsafe) {
        $Who = ($Unsafe | ForEach-Object { $_.IdentityReference.Value } | Sort-Object -Unique) -join ', '
        Write-Error ("Not only administrators can change '$Path' ($Who). Move the app to a folder that only " +
                     "administrators can change, for example C:\Program Files\XY-MD02_WebApp, and run this script again.")
        exit 1
    }
}

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

# LOCAL SERVICE cannot read other users' profile folders: Python must be installed for all users
$BasePrefix = (& $VenvPython -c 'import sys; print(sys.base_prefix)').Trim()
if ($BasePrefix -like "$env:SystemDrive\Users\*") {
    Write-Error ("Python is installed for one user only ($BasePrefix). Reinstall Python from python.org with " +
                 "'Install Python for all users' (Customize installation > Advanced Options), delete the .venv folder and run this script again.")
    exit 1
}

# The service account only needs to write the database and the log
foreach ($Folder in @('src', 'logs')) {
    $Dir = Join-Path $AppDir $Folder
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    icacls $Dir /grant '*S-1-5-19:(OI)(CI)M' | Out-Null   # LOCAL SERVICE: modify
}

# Scheduled task: at startup, as LOCAL SERVICE, no time limit, restart if the task itself fails
Write-Host "-> Registering scheduled task '$TaskName'"
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$Runner`"" -WorkingDirectory $AppDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\LOCAL SERVICE' -LogonType ServiceAccount -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskPrincipal `
    -Settings $taskSettings -Description 'XY-MD02 temperature and humidity WebApp' -Force | Out-Null

# Firewall: allow the web port
$Profiles = if ($AllowPublic) { 'Domain,Private,Public' } else { 'Domain,Private' }
Write-Host "-> Opening TCP port $Port in the Windows firewall ($Profiles networks)"
Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow `
    -Profile $Profiles | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5
Write-Host ''
Write-Host 'Installed. The app starts automatically at Windows startup, also without login.'
Write-Host "  Open:      http://localhost:$Port  (from other computers: http://<this-pc-ip>:$Port)"
Write-Host "  Logs:      $AppDir\logs\app.log"
Write-Host "  Status:    Get-ScheduledTask -TaskName '$TaskName' | Select-Object State"
Write-Host "  Uninstall: powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\uninstall-service.ps1`""
