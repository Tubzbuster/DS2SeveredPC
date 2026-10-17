@echo off
rem Drag one or more Severed add-on files (or unpacked folders) onto this file.
rem Writes <name>.addoninfo.txt next to it: header IDs and file hashes only.
rem Needs 64-bit Python 3 (python.org, "py" launcher).
setlocal
if "%~1"=="" (
  echo Usage: %~nx0 "add-on file or folder" [more ...]
  pause
  exit /b 1
)
py -3 "%~dp0addon_info.py" %*
echo.
pause
