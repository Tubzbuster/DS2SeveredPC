#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <vector>
#include <fstream>
#include <iterator>
#include "safetyhook/safetyhook.hpp"
extern "C" bool node_request_test(const void*);
extern "C" void* node_scan_level_test(BYTE*,size_t);
extern "C" bool node_attach_level_test(void*);
extern "C" void node_reset_level_test();
static int active=-1,notifications=0,core_calls=0,count=0;
extern "C" void ds2fix_campaign(int value){active=value;++notifications;}
extern "C" void ds2fix_install(int){}
extern "C" void ds2save_start(){}
static safetyhook::InlineHook core;
static int __fastcall core_detour(void* self,void*){++core_calls;return core.thiscall<int>(self);}
static void check(bool ok,const char* why){if(!ok){printf("FAIL %s\n",why);ExitProcess(1);}++count;printf("PASS %s\n",why);}
int main(int argc,char**argv){check(argc==2,"read-only fixture argument");std::ifstream f(argv[1],std::ios::binary);std::vector<BYTE> image((std::istreambuf_iterator<char>(f)),{});check(!image.empty(),"fixture readable");auto* found=static_cast<BYTE*>(node_scan_level_test(image.data(),image.size()));check(found!=nullptr,"real game suffix unique and validated");std::vector<BYTE> fixture(found-86,found+16);check(node_scan_level_test(fixture.data(),fixture.size())==fixture.data()+86,"observer boundary is after original 86-byte signature");fixture[0]=0xe9;memset(fixture.data()+1,0,4);fixture[5]=0x90;check(node_scan_level_test(fixture.data(),fixture.size())==fixture.data()+86,"core entry hook does not hide extras signature");auto twice=fixture;twice.insert(twice.end(),fixture.begin(),fixture.end());check(!node_scan_level_test(twice.data(),twice.size()),"duplicate layouts rejected");fixture[86]=0x90;check(!node_scan_level_test(fixture.data(),fixture.size()),"changed observer instructions rejected");
 BYTE request[0x60]{};const char* folder="pdlc1_ch01_mng";memcpy(request+0x28,&folder,4);check(node_request_test(request),"DLC campaign recognized independently");folder="PDLC1_CH01_MNG\\/";memcpy(request+0x28,&folder,4);check(node_request_test(request),"case and trailing separators accepted");for(const char* value:{"ds_2","frontend","unknown","pdlc1_ch01_mng_more",""}){folder=value;memcpy(request+0x28,&folder,4);check(!node_request_test(request),"non-DLC request left inactive");}check(!node_request_test(nullptr),"missing request rejected");folder=nullptr;memcpy(request+0x28,&folder,4);check(!node_request_test(request),"null folder rejected");char long_name[128];memset(long_name,'a',sizeof(long_name));folder=long_name;memcpy(request+0x28,&folder,4);check(!node_request_test(request),"unterminated folder rejected");
 for(int order=0;order<2;++order){auto* mem=static_cast<BYTE*>(VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE));check(mem!=nullptr,"isolated code allocated");memset(mem,0x90,256);BYTE start[]={0x81,0xec,0x40,0x01,0,0,0x55,0x8b,0xe9};memcpy(mem,start,sizeof(start));BYTE middle[]={0x6a,0,0x6a,0,0x83,0xc4,8,0x85,0xc0,0x5d,0x81,0xc4,0x40,1,0,0,0xb8,7,0,0,0,0xc3};memcpy(mem+82,middle,sizeof(middle));
 auto attachCore=[&](){auto hook=safetyhook::InlineHook::create(mem,reinterpret_cast<void*>(core_detour));check(bool(hook),"core hook attached");core=std::move(*hook);};
 if(order==0){check(node_attach_level_test(mem+86),"extras first attaches interior hook");check(!memcmp(mem,start,sizeof(start)),"extras leaves core prologue unchanged");attachCore();}else{attachCore();check(node_attach_level_test(mem+86),"extras after core attaches interior hook");}
 using Fn=int(__thiscall*)(void*);auto call=reinterpret_cast<Fn>(mem);folder="pdlc1_ch01_mng";memcpy(request+0x28,&folder,4);int old=notifications;check(call(request)==7&&active==1&&notifications==old+1,"coexisting hooks preserve return and observe DLC once");folder="ds_2";memcpy(request+0x28,&folder,4);check(call(request)==7&&active==0,"base-game transition clears DLC state");check(call(nullptr)==7&&active==0,"unknown request remains inactive with original return");core.reset();node_reset_level_test();check(VirtualFree(mem,0,MEM_RELEASE)!=0,"isolated hooks released");}
 check(core_calls==6,"core behavior called exactly once in both load orders");printf("ALL STANDALONE OBSERVER CHECKS PASSED %d\n",count);return 0;}
