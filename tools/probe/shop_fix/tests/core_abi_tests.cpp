#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
extern "C" void* ds2fix_core_ctor_test(void*,void*,void*);
static unsigned order=0;
static bool valid=true;
__declspec(noinline) static void* __fastcall fake_ctor(void* self,void*) {
    valid=valid && self==reinterpret_cast<void*>(0x12345678) && order==0;order=1;
    return reinterpret_cast<void*>(0x76543210);
}
__declspec(noinline) static void __fastcall fake_add(void* self,void*,const char* name,const char* desc,const char* folder,const char* streams,const char* checkpoint,int flags,int unlock,const char* extra) {
    valid=valid && self==reinterpret_cast<void*>(0x12345678) && order==1;
    valid=valid && !strcmp(name,"Dead Space 2: Severed") && !strcmp(desc,"Gabe Weller's story");
    valid=valid && !strcmp(folder,"pdlc1_ch01_mng") && !strcmp(streams,"pdlc1_ch01_mng.str");
    valid=valid && !strcmp(checkpoint,"XONTREALPR_CB22182_E50854D_v3") && flags==0 && unlock==0 && extra==nullptr;
    order=2;
}
int main() {
    auto result=ds2fix_core_ctor_test(reinterpret_cast<void*>(0x12345678),reinterpret_cast<void*>(&fake_ctor),reinterpret_cast<void*>(&fake_add));
    if(!valid || order!=2 || result!=reinterpret_cast<void*>(0x76543210)){puts("FAIL original constructor/AddEpisode x86 ABI");return 1;}
    puts("PASS original constructor/AddEpisode x86 ABI: ECX self, 8 stack arguments, order and return value");
}
