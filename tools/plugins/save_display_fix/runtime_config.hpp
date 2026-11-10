#pragma once
#include <windows.h>
#include <cwchar>
static bool severed_menu_ini_path(wchar_t* ini, DWORD capacity) {
    HMODULE own=nullptr;
    if(!ini || capacity==0 || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(&severed_menu_ini_path),&own)) return false;
    DWORD n=GetModuleFileNameW(own,ini,capacity);
    if(n==0 || n>=capacity) return false;
    wchar_t* slash=wcsrchr(ini,wchar_t(92));
    static const wchar_t filename[]=L"SeveredSaveDisplay.ini";
    if(!slash || size_t(slash-ini+1)+sizeof(filename)/sizeof(filename[0])>capacity) return false;
    return wcscpy_s(slash+1,capacity-size_t(slash-ini+1),filename)==0;
}
