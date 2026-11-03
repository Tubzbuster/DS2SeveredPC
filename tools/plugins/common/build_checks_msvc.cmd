@echo off
setlocal
if /I not "%VSCMD_ARG_TGT_ARCH%"=="x86" call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
if not exist build\temp mkdir build\temp
set "TEMP=%~dp0build\temp"
set "TMP=%TEMP%"
cl /nologo /c /O2 /MT /EHsc /std:c++latest /Fo:build\guard_module.obj tests\guard_module.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\guard-copy-a.dll build\guard_module.obj kernel32.lib advapi32.lib
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\guard-copy-b.dll build\guard_module.obj kernel32.lib advapi32.lib
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /Febuild\guard_host.exe /Fobuild\guard_host.obj tests\guard_host.cpp
if errorlevel 1 exit /b 1
build\guard_host.exe build\guard-copy-a.dll build\guard-copy-b.dll
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /Febuild\plugin_load_host.exe /Fobuild\plugin_load_host.obj tests\plugin_load_host.cpp
exit /b %errorlevel%
