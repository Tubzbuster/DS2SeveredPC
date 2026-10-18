@echo off
rem Copies the base game's hospital sections that Severed shares (the airless
rem hallway, the surgery ward) out of the PC archives into base_sections.zip,
rem to compare with Severed's. Usage:
rem   Extract-BaseSections.bat "<Dead Space 2 folder>" [section ...] [--all]
if "%~1"=="" (
  echo Usage: %~nx0 "Dead Space 2 folder" [section ...] [--all]
  exit /b 1
)
py -3 "%~dp0extract_base_sections.py" %*
pause
