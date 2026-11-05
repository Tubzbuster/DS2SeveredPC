@echo off
setlocal
if /I not "%VSCMD_ARG_TGT_ARCH%"=="x86" call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
if not exist build\temp mkdir build\temp
set "TEMP=%~dp0build\temp"
set "TMP=%TEMP%"
cl /nologo /c /O2 /MT /TC /Fo:build\Zydis.obj ..\common\vendor\safetyhook\Zydis.c
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Fo:build\safetyhook.obj ..\common\vendor\safetyhook\safetyhook.cpp
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Fo:build\plugin_main.obj plugin_main.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\SeveredMiningCampFix.asi build\plugin_main.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /DDS2MINING_TEST /I..\common\vendor /Fo:build\plugin_test.obj plugin_main.cpp
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Febuild\mining_tests.exe /Fobuild\mining_tests.obj tests\mining_tests.cpp build\plugin_test.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib /link /MACHINE:X86
if errorlevel 1 exit /b 1
build\mining_tests.exe
exit /b %errorlevel%
