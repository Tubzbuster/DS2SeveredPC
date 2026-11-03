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
cl /nologo /c /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Fo:build\save_titles.obj save_titles.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:build\SeveredSaveDisplay.asi build\plugin_main.obj build\save_titles.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib shell32.lib
if errorlevel 1 exit /b 1
cl /nologo /c /O2 /MT /EHsc /std:c++latest /DDS2SAVE_TEST /I..\common\vendor /Fo:build\save_test.obj save_titles.cpp
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++latest /I..\common\vendor /Febuild\save_title_tests.exe /Fobuild\save_title_tests.obj tests\save_title_tests.cpp build\save_test.obj build\safetyhook.obj build\Zydis.obj user32.lib kernel32.lib advapi32.lib shell32.lib /link /MACHINE:X86
if errorlevel 1 exit /b 1
if "%~2"=="" (
 echo APX fixture checks not run. Pass a fresh test directory and matching preview archive as arguments.
 exit /b 0
)
build\save_title_tests.exe "%~1" "%~2"
exit /b %errorlevel%
