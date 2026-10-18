@echo off
rem Builds the DS2SeveredPC app (dist\DS2SeveredPC\DS2SeveredPC.exe) with its own
rem Python inside: zip the dist\DS2SeveredPC folder to hand it out.
rem Needs 64-bit Python 3 and PyInstaller (py -3 -m pip install pyinstaller). For fewer
rem antivirus false alarms, install it with its launcher built from source, as the
rem workflow does: set PYINSTALLER_COMPILE_BOOTLOADER=1 and
rem py -3 -m pip install --no-binary pyinstaller pyinstaller (needs Visual Studio's C++ tools).
rem ffmpeg: put ffmpeg.exe and its LICENSE.txt in tools\app\ffmpeg\ first (an
rem LGPL build; the GitHub Actions workflow downloads one) and they are copied in.
setlocal
cd /d "%~dp0"
set R=..\research
rem PYTHON (environment) picks the Python to build with; else the py launcher
if defined PYTHON (set "PY=%PYTHON%") else (set "PY=py -3")
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name DS2SeveredPC ^
  --version-file version_info.txt --icon icon.ico --add-data "icon.ico;." --add-data "icon.png;." ^
  --paths ..\test --paths %R% --hidden-import make_severed_test --collect-submodules ds2 ^
  --add-data "%R%\ds2\*.pkl;ds2" --add-data "%R%\ds2\*.json;ds2" --add-data "%R%\ds2\*.txt;ds2" ^
  --add-binary "%R%\native\xasenc.dll;native" ^
  --add-data "..\probe\bin\dinput8.dll;hook" ^
  severed_installer.py || exit /b 1
if exist ffmpeg\ffmpeg.exe (
  xcopy /y /i ffmpeg dist\DS2SeveredPC\ffmpeg >nul
  echo ffmpeg bundled
) else (
  echo ffmpeg not bundled: the wizard will ask for ffmpeg.exe
)
copy /y ..\..\LICENSE dist\DS2SeveredPC\LICENSE.txt >nul
copy /y "Keep all files together in the same folder.txt" dist\DS2SeveredPC\ >nul
if not "%1"=="nopause" pause
