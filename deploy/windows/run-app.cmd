@echo off
rem Runs the XY-MD02 WebApp and restarts it when it stops. Started by the scheduled task
rem "XY-MD02 WebApp" (see install-service.ps1). Output is appended to logs\app.log.
cd /d "%~dp0..\.."
if not exist logs mkdir logs
set PYTHONUNBUFFERED=1
:loop
echo [%date% %time%] Starting XY-MD02 WebApp >> "logs\app.log"
rem Full path to app.py: also visible in the command line of the real python process (venv redirector)
".venv\Scripts\python.exe" "%CD%\app.py" >> "logs\app.log" 2>&1
echo [%date% %time%] App stopped (exit code %errorlevel%), restarting in 10 seconds >> "logs\app.log"
timeout /t 10 /nobreak >nul
goto loop
