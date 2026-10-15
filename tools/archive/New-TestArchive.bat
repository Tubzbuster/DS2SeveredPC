@echo off
rem Creates (or removes) the test archive DS2DAT2.DAT in the Dead Space 2 folder.
setlocal
set "SCRIPT=%~dp0New-TestArchive.ps1"
set /p "GAMEDIR=Dead Space 2 folder (with deadspace2.exe): "
set "ACTION="
set /p "ACTION=Type R to remove the test archive, or press Enter to create it: "
if /i "%ACTION%"=="R" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -GameDir "%GAMEDIR%" -Remove
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -GameDir "%GAMEDIR%"
)
echo.
pause
