@echo off
setlocal
if /I not "%VSCMD_ARG_TGT_ARCH%"=="x86" call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
if not exist build\temp mkdir build\temp
set "TEMP=%~dp0build\temp"
set "TMP=%TEMP%"
cl /nologo /c /O2 /MT /TP /EHsc /std:c++latest /DSEVERED_ASI /DSEVERED_NODE_FIX /Fo:build\probe_core.obj ..\probe.c
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /TC /Fo:build\Zydis.obj vendor\safetyhook\Zydis.c
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /Ivendor /Fo:build\safetyhook.obj vendor\safetyhook\safetyhook.cpp
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /Ivendor /Fo:build\shop_runtime.obj shop_runtime.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\SeveredPC.asi build\probe_core.obj build\shop_runtime.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /DDS2FIX_TEST /Ivendor /Fo:build\shop_runtime_test.obj shop_runtime.cpp
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /Ivendor /Febuild\shop_policy_tests.exe /Fobuild\shop_policy_tests.obj tests\shop_policy_tests.cpp build\shop_runtime_test.obj build\safetyhook.obj build\Zydis.obj /link /MACHINE:X86
if errorlevel 1 exit /b 1
build\shop_policy_tests.exe
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /TP /EHsc /std:c++latest /DSEVERED_ASI /DDS2FIX_CORE_TEST /Fo:build\probe_core_stock_test.obj ..\probe.c
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /Febuild\core_abi_stock_tests.exe /Fobuild\core_abi_stock_tests.obj tests\core_abi_tests.cpp build\probe_core_stock_test.obj user32.lib kernel32.lib /link /MACHINE:X86
if errorlevel 1 exit /b 1
build\core_abi_stock_tests.exe
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /TP /EHsc /std:c++latest /DSEVERED_ASI /DSEVERED_NODE_FIX /DDS2FIX_CORE_TEST /Fo:build\probe_core_test.obj ..\probe.c
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /Febuild\core_abi_tests.exe /Fobuild\core_abi_tests.obj tests\core_abi_tests.cpp build\probe_core_test.obj build\shop_runtime.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib /link /MACHINE:X86
if errorlevel 1 exit /b 1
build\core_abi_tests.exe
exit /b %errorlevel%
