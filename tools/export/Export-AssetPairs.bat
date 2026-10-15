@echo off
rem Exports the assets listed in wanted.txt from the PC and Xbox 360 archives
rem into an "out" folder next to this file (out\assets_export.zip).
setlocal
set "SCRIPT=%~dp0Export-AssetPairs.ps1"
set /p "GAMEDIR=PC Dead Space 2 folder (with DS2DAT0.DAT): "
set /p "X360DIR=Extracted Xbox 360 discs folder (with the .viv files): "
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -GameDir "%GAMEDIR%" -X360Dir "%X360DIR%"
echo.
pause
