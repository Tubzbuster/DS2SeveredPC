#define WIN32_LEAN_AND_MEAN
#include "../mining_runtime.hpp"
#include "../../common/vendor/safetyhook/safetyhook.hpp"
#include <cstdio>
extern "C" void mining_invoke_test(safetyhook::Context&);
extern "C" bool mining_attach_test(void*);
extern "C" void mining_reset_test();
extern "C" uintptr_t mining_last_actor_test();
static unsigned checks=0;
static void check(bool yes,const char* name){printf("%s %s\n",yes?"PASS":"FAIL",name);if(!yes)ExitProcess(1);++checks;}
static void put(BYTE* p,DWORD v){memcpy(p,&v,4);}
static BYTE actor[0x58],savedActor[0x58],savedConfig[32];
static BYTE* config=nullptr;
static void prepare(){memset(actor,0xCD,sizeof(actor));memset(config,0xEF,32);const DWORD guid[]={0x4FCB8B7D,0x0206C813,0x4952414D,0x4C4C454E};memcpy(actor+0x24,guid,16);put(actor+0x34,0xEB27FF6B);put(actor+12,(DWORD)(uintptr_t)config);put(config,0x442FCCC9);put(config+12,0);put(config+16,1);}
__declspec(naked) static DWORD __fastcall synthetic_constructor(void*,void*){__asm {
 push esi
 mov esi,ecx
 mov eax,13579BDFh
 pop esi
 ret
}}
int main(){
 setvbuf(stdout,nullptr,_IONBF,0); config=(BYTE*)VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);check(config!=nullptr,"isolated parameter page allocated");
 prepare();memcpy(savedActor,actor,sizeof(actor));memcpy(savedConfig,config,32);
 safetyhook::Context c{};c.esi=(DWORD)(uintptr_t)actor;mining_invoke_test(c);
 check(mining_camp::word(config+16)==0,"exact initializer becomes repeatable");
 check(!memcmp(actor,savedActor,sizeof(actor)),"actor, GUID and progression fields unchanged");
 put(savedConfig+16,0);check(!memcmp(config,savedConfig,32),"only options word changes; target, delay and string relocation retained");
 for(unsigned offset:{0x24u,0x28u,0x2Cu,0x30u,0x34u}){prepare();actor[offset]^=1;memcpy(savedConfig,config,32);mining_invoke_test(c);check(!memcmp(config,savedConfig,32),"different object identity refused");}
 for(unsigned offset:{0u,12u,16u}){prepare();config[offset]^=4;memcpy(savedConfig,config,32);mining_invoke_test(c);check(!memcmp(config,savedConfig,32),"different target, delay or flags refused");}
 prepare();put(config+16,0);mining_invoke_test(c);check(mining_camp::word(config+16)==0,"already corrected initializer unchanged");
 prepare();put(actor+12,0);mining_invoke_test(c);check(mining_camp::word(config+16)==1,"missing configuration refused");c.esi=0;mining_invoke_test(c);check(true,"missing actor ignored");
 prepare();DWORD old;check(VirtualProtect(config,32,PAGE_READONLY,&old)!=0,"readonly fixture protected");c.esi=(DWORD)(uintptr_t)actor;mining_invoke_test(c);check(mining_camp::word(config+16)==1,"read-only parameters never made writable");VirtualProtect(config,32,old,&old);
 auto* body=(BYTE*)&synthetic_constructor;BYTE* site=nullptr;for(unsigned i=0;i<20;++i)if(body[i]==0xB8){site=body+i;break;}
 check(site&&mining_attach_test(site),"real x86 MidHook attaches after constructed object is in ESI");prepare();uintptr_t before,after;__asm mov before,esp
 DWORD result; __asm { lea ecx,actor
 call synthetic_constructor
 mov result,eax
 }
 __asm mov after,esp
 check(before==after&&result==0x13579BDF,"constructor registers, stack and return preserved");check(mining_camp::word(config+16)==0,"real hook corrects parameters through ESI");mining_reset_test();
 printf("ALL MINING CHECKS PASSED %u\n",checks);return 0;
}
