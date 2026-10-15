@echo off
rem Double-click (or drag a folder onto this file) to run the DS2 file scanner.
rem Bypasses the PowerShell script-execution policy for this one run only.
setlocal
set "SCRIPT=%~dp0Scan-DS2Files.ps1"
set "TARGET=%~1"
if "%TARGET%"=="" set /p "TARGET=Folder to scan: "
set /p "LABEL=Label for this scan (PC, Severed360 or Base360): "
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Path "%TARGET%" -Label "%LABEL%"
echo.
pause
