@echo off
rem Builds the DS2SeveredPC app (dist\DS2SeveredPC\DS2SeveredPC.exe) with its own
rem Python inside: zip the dist\DS2SeveredPC folder to hand it out.
rem Needs 64-bit Python 3 and PyInstaller (py -3 -m pip install pyinstaller).
setlocal
cd /d "%~dp0"
set R=..\research
py -3 -m PyInstaller --noconfirm --clean --onedir --windowed --name DS2SeveredPC ^
  --paths ..\test --paths %R% --hidden-import make_severed_test --collect-submodules ds2 ^
  --add-data "%R%\ds2\*.pkl;ds2" --add-data "%R%\ds2\*.json;ds2" --add-data "%R%\ds2\*.txt;ds2" ^
  --add-binary "%R%\native\xasenc.dll;native" ^
  severed_installer.py
echo.
pause
