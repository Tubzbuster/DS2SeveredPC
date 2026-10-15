@echo off
rem Lists every asset header in the PC game's streams and in the extracted
rem Severed folder. Output: an "out" folder next to this file (out\assets.zip).
setlocal
set "SCRIPT=%~dp0Index-Assets.ps1"
set /p "GAMEDIR=PC Dead Space 2 folder (with DS2DAT0.DAT): "
set /p "SEVDIR=Extracted Severed folder (with weller1.lvl): "
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -GameDir "%GAMEDIR%" -SeveredDir "%SEVDIR%"
echo.
pause
