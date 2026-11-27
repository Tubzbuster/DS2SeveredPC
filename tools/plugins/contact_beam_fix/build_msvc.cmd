@echo off
setlocal
set "status=1"
where cl.exe >nul 2>&1
if errorlevel 1 (
    echo Open an x86 Native Tools Command Prompt for Visual Studio 2022 first.
    exit /b 1
)
pushd "%~dp0" || exit /b 1
if not exist build mkdir build
set "common=..\common"
set "hook=%common%\vendor\safetyhook"

cl /nologo /c /O2 /MT /TC /Fo:build\Zydis.obj "%hook%\Zydis.c" || goto done
cl /nologo /c /O2 /MT /EHsc /std:c++latest /I"%common%\vendor" /Fo:build\safetyhook.obj "%hook%\safetyhook.cpp" || goto done
cl /nologo /c /O2 /MT /EHsc /utf-8 /std:c++latest /I"%common%" /I"%common%\vendor" /Fo:build\plugin.obj plugin_main.cpp || goto done
link /nologo /DLL /MACHINE:X86 /OUT:build\SeveredContactBeamFix.asi build\plugin.obj build\safetyhook.obj build\Zydis.obj bcrypt.lib || goto done
cl /nologo /O2 /MT /EHsc /utf-8 /std:c++latest /DCONTACT_BEAM_TEST /I"%common%" /I"%common%\vendor" /Fo:build\hook_test.obj /Fe:build\hook_test.exe plugin_main.cpp build\safetyhook.obj build\Zydis.obj bcrypt.lib /link /MACHINE:X86 || goto done
set "status=0"
:done
popd
exit /b %status%
