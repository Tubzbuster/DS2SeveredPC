@echo off
rem Exports the sample files listed in Export-Samples.ps1 into an "out" folder
rem next to this file, and zips them (out\samples.zip). Leave a folder blank
rem to skip it.
setlocal
set "SCRIPT=%~dp0Export-Samples.ps1"
set /p "PCDIR=PC Dead Space 2 folder (with DS2DAT0.DAT): "
set /p "X360DIR=Extracted Xbox 360 discs folder (with the .viv files): "
set /p "SEVDIR=Extracted Severed folder (with weller1.lvl): "
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -PcDir "%PCDIR%" -X360Dir "%X360DIR%" -SeveredDir "%SEVDIR%"
echo.
pause
