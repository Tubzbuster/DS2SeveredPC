#define WIN32_LEAN_AND_MEAN
#include "../common/plugin_support.hpp"
#include "../common/vendor/safetyhook/safetyhook.hpp"
#include "mining_runtime.hpp"
#include <atomic>
namespace {
plugin_support::Log log_file;
safetyhook::MidHook hook;
std::atomic_uint corrected{0};
#ifdef DS2MINING_TEST
uintptr_t testActor=0;
#endif
bool writable(void* p,size_t bytes) {
 MEMORY_BASIC_INFORMATION m{};
 return plugin_support::readable(p,bytes)&&VirtualQuery(p,&m,sizeof(m))
     &&(m.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY));
}
void on_constructed(safetyhook::Context& ctx) {
#ifdef DS2MINING_TEST
 testActor=ctx.esi;
#endif
 auto* actor=reinterpret_cast<BYTE*>(ctx.esi);
 if(!plugin_support::readable(actor,0x58))return;
 auto* config=reinterpret_cast<BYTE*>(mining_camp::word(actor+0x0C));
 if(!writable(config,20))return;
 if(mining_camp::correct(actor,config)&&corrected.fetch_add(1)<8)
   log_file.write("MINING_INIT corrected exact mining-camp initializer in memory; DAT and saves unchanged");
}
BYTE* validate(BYTE* fn) {
 // Stop if either the derived constructor or its base no longer has the
 // verified ABI. The hook runs after base construction, before subscription.
 if(!plugin_support::readable(fn,47))return nullptr;
 const BYTE head[]={0x8B,0x44,0x24,0x04,0x56,0x50,0x8B,0xF1,0xE8};
 const BYTE tail[]={0x68,0xFF,0x7F,0,0,0x68};
 const BYTE registers[]={0x8B,0xCE,0xC7,0x06};
 if(memcmp(fn,head,sizeof(head))||memcmp(fn+13,tail,sizeof(tail))||memcmp(fn+23,registers,sizeof(registers)))return nullptr;
 int displacement;memcpy(&displacement,fn+9,4);
 auto* base=fn+13+displacement;
 const BYTE baseHead[]={0x53,0x8B,0x5C,0x24,0x08,0x8B,0x43,0x10,0x56,0x8B,0xF1,0x57,0x83,0xC0,0x10};
 const BYTE config[]={0x89,0x46,0x0C};
 const BYTE guid[]={0x89,0x56,0x24,0x8B,0x51,0x04,0x89,0x56,0x28,0x8B,0x51,0x08,0x89,0x56,0x2C,0x8B,0x49,0x0C,0x89,0x4E,0x30};
 if(!plugin_support::readable(base,0x90)||memcmp(base,baseHead,sizeof(baseHead))||memcmp(base+0x25,config,sizeof(config))||memcmp(base+0x52,guid,sizeof(guid)))return nullptr;
 return fn+13;
}
DWORD WINAPI start(void*) {
 wchar_t ini[MAX_PATH]{};if(!plugin_support::own_path(reinterpret_cast<void*>(&start),L"SeveredMiningCampFix.ini",ini,MAX_PATH))return 0;
 if(GetPrivateProfileIntW(L"MiningCamp",L"InitializationFix",0,ini)!=1)return 0;
 log_file.open(reinterpret_cast<void*>(&start),L"SeveredMiningCampFix.log");
 const char* pattern="8B 44 24 04 56 50 8B F1 E8 ?? ?? ?? ?? 68 FF 7F 00 00 68 ?? ?? ?? ?? 8B CE C7 06 ?? ?? ?? ?? C7 46 10 ?? ?? ?? ?? E8 ?? ?? ?? ?? 8B C6 5E C2 04 00";
 for(unsigned attempt=0;attempt<600;++attempt) {
   auto* fn=plugin_support::scan_game(pattern);
   if(fn){auto* site=validate(fn);if(!site){log_file.write("MINING_INIT unsupported base layout; unchanged");return 0;}
     plugin_support::PatchGuard guard;if(!guard.ready()){log_file.write("MINING_INIT patch coordination unavailable; unchanged");return 0;}
     auto result=safetyhook::MidHook::create(site,on_constructed);
     if(result){hook=std::move(*result);log_file.write("MINING_INIT constructor hooked; only GUID 4FCB8B7D-0206C813-4952414D-4C4C454E eligible");}
     else log_file.write("MINING_INIT hook failed; unchanged");return 0;
   }Sleep(500);
 }log_file.write("MINING_INIT constructor unavailable; unchanged");return 0;
}
}
BOOL WINAPI DllMain(HINSTANCE own,DWORD reason,LPVOID) {
 if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(own);if(plugin_support::game_host()){HANDLE t=CreateThread(nullptr,0,start,nullptr,0,nullptr);if(t)CloseHandle(t);}}return TRUE;
}
#ifdef DS2MINING_TEST
extern "C" void mining_invoke_test(safetyhook::Context& ctx){on_constructed(ctx);}
extern "C" void* mining_validate_test(BYTE* p){return validate(p);}
extern "C" bool mining_attach_test(void* p){auto result=safetyhook::MidHook::create(p,on_constructed);if(!result)return false;hook=std::move(*result);return true;}
extern "C" void mining_reset_test(){hook.reset();}
extern "C" uintptr_t mining_last_actor_test(){return testActor;}
#endif
