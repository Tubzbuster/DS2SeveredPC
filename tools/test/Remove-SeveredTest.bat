@echo off
rem Removes the Severed test archive: Remove-SeveredTest.bat "<Dead Space 2 folder>"
if "%~1"=="" (
  echo Usage: %~nx0 "Dead Space 2 folder"
  exit /b 1
)
py -3 "%~dp0make_severed_test.py" --game "%~1" --remove
pause
