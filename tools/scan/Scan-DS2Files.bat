@echo off
rem Double-click (or drag a folder onto this file) to run the DS2 file scanner.
rem Results go into a "scans" folder next to this file.
rem Bypasses the PowerShell script-execution policy for this one run only.
setlocal
set "SCRIPT=%~dp0Scan-DS2Files.ps1"
set "TARGET=%~1"
if "%TARGET%"=="" set /p "TARGET=Folder to scan: "
set /p "LABEL=Label for this scan (PC, Severed360 or Base360): "
set "EXTRACT="
set /p "EXTRACT=Also extract Xbox 360 package contents to an 'extracted' folder here? (y/N): "
if /i "%EXTRACT%"=="y" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Path "%TARGET%" -Label "%LABEL%" -ExtractTo "%~dp0extracted"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Path "%TARGET%" -Label "%LABEL%"
)
echo.
pause
