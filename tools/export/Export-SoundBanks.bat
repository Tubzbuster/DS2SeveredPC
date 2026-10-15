@echo off
rem Exports the sound banks listed in wanted_sbk.txt from the PC and Xbox 360
rem archives into an "out_sbk" folder next to this file (out_sbk\assets_export.zip).
setlocal
set "SCRIPT=%~dp0Export-AssetPairs.ps1"
set /p "GAMEDIR=PC Dead Space 2 folder (with DS2DAT0.DAT): "
set /p "X360DIR=Extracted Xbox 360 discs folder (with the .viv files): "
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -GameDir "%GAMEDIR%" -X360Dir "%X360DIR%" -ListFile "%~dp0wanted_sbk.txt" -OutDir "%~dp0out_sbk"
echo.
pause
