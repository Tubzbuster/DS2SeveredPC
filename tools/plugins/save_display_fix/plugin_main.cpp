#define WIN32_LEAN_AND_MEAN
#include "../common/plugin_support.hpp"
#include "runtime_config.hpp"
static plugin_support::Log log_file;
static const char kSave[]="B8 94 10 00 00 E8 ?? ?? ?? ?? 8B 84 24 A4 10 00 00 55 56 57 8B BC 24 A4 10 00 00 89 07 8B 84 24 AC 10 00 00 8D 34 80 03 F6 03 F6 8B E9 8B 8D F8 02 00 00";
extern "C" void ds2save_start();
extern "C" void ds2save_log(const char* text){log_file.write(text);}
extern "C" void* ds2save_find_builder(){return plugin_support::scan_game(kSave);}
static DWORD WINAPI start(void*) {
 wchar_t ini[MAX_PATH]{};if(!severed_menu_ini_path(ini,MAX_PATH))return 0;
 if(GetPrivateProfileIntW(L"SaveDisplay",L"TitleFix",0,ini)!=1&&GetPrivateProfileIntW(L"SaveDisplay",L"IconFix",0,ini)!=1)return 0;
 log_file.open(reinterpret_cast<const void*>(&start),L"SeveredSaveDisplay.log");log_file.write("Optional standalone DLC save-display ASI enabled; saves remain read-only");
 if(plugin_support::known_combined_loaded()){log_file.write("DISABLED: known combined local fixes already loaded; use only one implementation");return 0;}
 ds2save_start();return 0;
}
BOOL WINAPI DllMain(HINSTANCE own,DWORD why,LPVOID){if(why==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(own);if(plugin_support::game_host()){HANDLE thread=CreateThread(nullptr,0,start,nullptr,0,nullptr);if(thread)CloseHandle(thread);}}return TRUE;}
