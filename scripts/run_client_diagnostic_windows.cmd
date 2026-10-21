@echo off
setlocal
powershell.exe -NoLogo -NoProfile -File "%~dp0client_diagnostic_windows.ps1" -OutputPath "%~dp0netpilot-client-diagnostic.json"
if errorlevel 1 goto failed
echo Network check complete. Select netpilot-client-diagnostic.json on the NetPilot page.
pause
exit /b 0
:failed
echo Network check could not run. If blocked by your organization, skip this check in NetPilot.
echo Do not disable security policies. No result was uploaded.
pause
exit /b 1
