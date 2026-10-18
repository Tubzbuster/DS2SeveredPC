@echo off
rem Builds the DS2SeveredPC app (dist\DS2SeveredPC\DS2SeveredPC.exe) with its own
rem Python inside: zip the dist\DS2SeveredPC folder to hand it out.
rem Needs 64-bit Python 3 and PyInstaller (py -3 -m pip install pyinstaller).
rem ffmpeg: put ffmpeg.exe and its LICENSE.txt in tools\app\ffmpeg\ first (an
rem LGPL build; the GitHub Actions workflow downloads one) and they are copied in.
setlocal
cd /d "%~dp0"
set R=..\research
set PY=py -3
where py >nul 2>nul || set PY=python
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name DS2SeveredPC ^
  --paths ..\test --paths %R% --hidden-import make_severed_test --collect-submodules ds2 ^
  --add-data "%R%\ds2\*.pkl;ds2" --add-data "%R%\ds2\*.json;ds2" --add-data "%R%\ds2\*.txt;ds2" ^
  --add-binary "%R%\native\xasenc.dll;native" ^
  severed_installer.py || exit /b 1
if exist ffmpeg\ffmpeg.exe (
  xcopy /y /i ffmpeg dist\DS2SeveredPC\ffmpeg >nul
  echo ffmpeg bundled
) else (
  echo ffmpeg not bundled: the wizard will ask for ffmpeg.exe
)
copy /y ..\..\LICENSE dist\DS2SeveredPC\LICENSE.txt >nul
if not "%1"=="nopause" pause
