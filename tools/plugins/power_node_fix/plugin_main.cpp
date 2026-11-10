#define WIN32_LEAN_AND_MEAN
#include "../common/plugin_support.hpp"
#include "safetyhook/safetyhook.hpp"
using plugin_support::readable;
using plugin_support::scan_bytes;
using plugin_support::scan_game;
static plugin_support::Log boot_log;
static safetyhook::MidHook g_level;
extern "C" void ds2fix_install(int);
extern "C" void ds2fix_campaign(int);
static const char kLevel[]="53 55 8B E9 C7 45 18 07 00 00 00 A1 ?? ?? ?? ?? 8B 40 38 D1 E8 24 01 88 44 24 0A 8A 45 1C D0 E8 24 01 83 7D 4C 00 56 8D 75 28 88 44 24 0F 8B 06 0F 95 44 24 10 57 85 C0 75 05 B8 ?? ?? ?? ?? 68 ?? ?? ?? ?? 50 E8 ?? ?? ?? ?? 8B 0D ?? ?? ?? ??";
static bool severed_request(const void* request) {
 if(!readable(request,0x2c))return false;const char* folder=nullptr;memcpy(&folder,static_cast<const BYTE*>(request)+0x28,4);if(!folder)return false;
 char text[128]{};size_t n=0;for(;n<sizeof(text);++n){if(!readable(folder+n,1))return false;text[n]=folder[n];if(!text[n])break;}if(n==sizeof(text))return false;
 while(n&&(text[n-1]=='\\'||text[n-1]=='/'))text[--n]=0;
 return _stricmp(text,"pdlc1_ch01_mng")==0;
}
static void observe_level(safetyhook::Context& ctx){ds2fix_campaign(severed_request(reinterpret_cast<void*>(ctx.ebp))?1:0);}
static BYTE* level_site(BYTE* anchor){static const BYTE expected[]={0x83,0xc4,0x08,0x85,0xc0,0x0f,0x95,0xc3};BYTE* site=anchor?anchor+80:nullptr;return readable(site,sizeof(expected))&&!memcmp(site,expected,sizeof(expected))?site:nullptr;}

static DWORD WINAPI start(void*) {
 wchar_t ini[MAX_PATH]{};if(!plugin_support::own_path(reinterpret_cast<const void*>(&start),L"SeveredNodeFix.ini",ini,MAX_PATH)||GetPrivateProfileIntW(L"Shop",L"EnablePowerNodeShopFix",0,ini)!=1)return 0;
 boot_log.open(reinterpret_cast<const void*>(&start),L"SeveredPowerNodeFix.bootstrap.log");boot_log.write("Optional standalone Power Node ASI enabled; original DLC core unchanged");
 if(plugin_support::known_combined_loaded()){boot_log.write("DISABLED: known combined local fixes already loaded; use only one implementation");return 0;}
 for(unsigned n=0;n<300;++n){BYTE* anchor=scan_game(kLevel);if(anchor){BYTE* site=level_site(anchor);if(!site){boot_log.write("DISABLED: unknown level layout");return 0;}plugin_support::PatchGuard guard;if(!guard.ready()){boot_log.write("DISABLED: patch coordination unavailable");return 0;}auto hook=safetyhook::MidHook::create(site,observe_level);if(!hook){boot_log.write("DISABLED: level observer could not attach");return 0;}g_level=std::move(*hook);boot_log.write("Independent level observer attached after original 86-byte entry signature");ds2fix_install(1);return 0;}Sleep(200);}
 boot_log.write("DISABLED: level observer unavailable");return 0;
}
#ifndef DS2NODE_TEST
BOOL WINAPI DllMain(HINSTANCE own,DWORD why,LPVOID){if(why==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(own);if(plugin_support::game_host()){HANDLE thread=CreateThread(nullptr,0,start,nullptr,0,nullptr);if(thread)CloseHandle(thread);}}return TRUE;}
#else
extern "C" bool node_request_test(const void* p){return severed_request(p);}
extern "C" void* node_scan_level_test(BYTE* data,size_t size){return level_site(scan_bytes(data,size,kLevel));}
extern "C" bool node_attach_level_test(void* site){auto hook=safetyhook::MidHook::create(site,observe_level);if(!hook)return false;g_level=std::move(*hook);return true;}
extern "C" void node_reset_level_test(){g_level.reset();}
#endif
