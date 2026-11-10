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
cl /nologo /c /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Fo:build\shop_runtime.obj shop_runtime.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\SeveredPowerNodeFix.asi build\plugin_main.obj build\shop_runtime.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib shell32.lib
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /DDS2FIX_TEST /I..\common\vendor /Fo:build\shop_test.obj shop_runtime.cpp
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Febuild\shop_policy_tests.exe /Fobuild\shop_policy_tests.obj tests\shop_policy_tests.cpp build\shop_test.obj build\safetyhook.obj build\Zydis.obj /link /MACHINE:X86
if errorlevel 1 exit /b 1
build\shop_policy_tests.exe
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /DDS2NODE_TEST /I..\common\vendor /Fo:build\plugin_test.obj plugin_main.cpp
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Febuild\observer_tests.exe /Fobuild\observer_tests.obj tests\observer_tests.cpp build\plugin_test.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib shell32.lib /link /MACHINE:X86
if errorlevel 1 exit /b 1
if "%~1"=="" (
 echo Optional observer fixture checks not run. Pass a compatible original game EXE as the first argument.
 exit /b 0
)
build\observer_tests.exe "%~1"
exit /b %errorlevel%
