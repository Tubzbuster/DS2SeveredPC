@echo off
rem Builds the Severed test archive (DS2DAT2.DAT) in the Dead Space 2 folder.
rem   Make-SeveredTest.bat "<Severed addon file>" "<Dead Space 2 folder>" "<ffmpeg.exe>"
rem Needs 64-bit Python 3 (python.org, "py" launcher) and ffmpeg.
rem About 10 GB free space next to the addon file and 3.5 GB in the game folder.
setlocal
if "%~3"=="" (
  echo Usage: %~nx0 "Severed addon file" "Dead Space 2 folder" "ffmpeg.exe"
  exit /b 1
)
py -3 "%~dp0make_severed_test.py" --severed "%~1" --game "%~2" --ffmpeg "%~3"
echo.
pause
