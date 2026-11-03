#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include "safetyhook/safetyhook.hpp"
#include "../store_policy.hpp"
extern "C" bool ds2fix_test_attach(void*,void*,int,bool);
extern "C" bool ds2fix_test_attach_fallback(void*,void*,int,bool);
extern "C" void ds2fix_test_mode(int,bool);
extern "C" void ds2fix_test_reset();
extern "C" bool ds2fix_test_jump_owner(void*,HMODULE);

struct Entry {ds2fix::Guid guid;unsigned price;BYTE other[5];BYTE skip;BYTE rest[6];};
static_assert(offsetof(Entry,skip)==0x19);
static safetyhook::InlineHook marker;
static safetyhook::InlineHook marker_list;
static int marker_calls=0;
static bool entitlement=true;
static unsigned checks=0;
static void expect(bool condition,const char* name) {++checks;if(!condition){printf("FAIL %s\n",name);ExitProcess(1);}}

__declspec(noinline) static int __fastcall target(int self,int,Entry* e) {
    if(self!=0x12345678 || !entitlement)return -7;
    if(!e->skip)return 0; // representative chapter gate
    e->rest[0]=0x5a;     // other game-owned entry state must survive
    return static_cast<int>(e->price);
}
static int __fastcall existing_marker(int self,int,Entry* e) {
    ++marker_calls;return marker.thiscall<int>(self,e);
}
using Fn=int(__fastcall*)(int,int,Entry*);
static Fn volatile raw_call=&target;
static Entry* current_entry=nullptr;
static int current_result=0;
__declspec(noinline) static void __fastcall list_target(int self,int) {current_result=raw_call(self,0,current_entry);}
static void __fastcall existing_list(int self,int) {marker_list.thiscall<void>(self);}
static int __fastcall store_call(int self,int,Entry* entry) {
    current_entry=entry;
    using List=void(__fastcall*)(int,int);List volatile invoke=&list_target;
    invoke(self,0);return current_result;
}
int main() {
    Fn volatile call=&store_call;
    Entry node{};node.guid=ds2fix::power_node;node.price=10000;
    expect(call(0x12345678,0,&node)==0,"baseline gate active");
    // Exercise the real production hook through an already-installed JMP,
    // matching the game's MarkerPatch -> original hook chain.
    marker=safetyhook::create_inline(reinterpret_cast<void*>(&target),reinterpret_cast<void*>(&existing_marker));
    marker_list=safetyhook::create_inline(reinterpret_cast<void*>(&list_target),reinterpret_cast<void*>(&existing_list));
    expect(static_cast<bool>(marker),"existing hook installed");
    expect(static_cast<bool>(marker_list),"existing list hook installed");
    expect(ds2fix_test_jump_owner(reinterpret_cast<void*>(&target),GetModuleHandleW(nullptr)),"allocated item relay resolves actual owner");
    expect(ds2fix_test_jump_owner(reinterpret_cast<void*>(&list_target),GetModuleHandleW(nullptr)),"allocated list relay resolves actual owner");
    expect(ds2fix_test_attach(reinterpret_cast<void*>(&target),reinterpret_cast<void*>(&list_target),1,true),"production hooks chained over existing hooks");
    expect(call(0x12345678,0,&node)==10000,"node offered in Severed node profile");
    expect(marker_calls==1,"existing hook still called");
    expect(node.skip==0,"temporary gate byte restored");
    expect(node.price==10000 && node.rest[0]==0x5a,"price and other game updates preserved");
    expect(raw_call(0x12345678,0,&node)==0,"outside store-list population remains unchanged");
    ds2fix_test_mode(1,false);
    expect(call(0x12345678,0,&node)==0,"base campaign unchanged");
    ds2fix_test_mode(0,true);
    expect(call(0x12345678,0,&node)==0,"observe-only profile unchanged");
    ds2fix_test_mode(1,true);
    entitlement=false;
    expect(call(0x12345678,0,&node)==-7,"entitlement decision not overridden");
    expect(node.skip==0,"restored after rejected item");entitlement=true;
    Entry weapon{};weapon.guid={{0x36C8BC4F,0x67BB5F38,0x44455257,0x34303245}};weapon.price=7000;
    expect(call(0x12345678,0,&weapon)==0,"node-only profile leaves other item gated");
    ds2fix_test_mode(2,true);
    expect(call(0x12345678,0,&node)==0,"unsupported mode two does not unlock nodes");
    expect(call(0x12345678,0,&weapon)==0,"unsupported mode two does not unlock weapons");
    Entry unknown{};unknown.guid={{1,2,3,4}};unknown.price=1;
    expect(call(0x12345678,0,&unknown)==0,"unknown item remains gated");
    Entry suit{};suit.guid={{0x31CBB1C4,0xE85D26F3,0,0}};
    expect(call(0x12345678,0,&suit)==0,"removed suit is not restored");
    node.skip=1;expect(call(0x12345678,0,&node)==10000 && node.skip==1,"pre-existing bypass flag retained");
    node.skip=0;ds2fix_test_mode(99,true);
    expect(call(0x12345678,0,&node)==0,"invalid profile changes nothing");
    ds2fix_test_reset();
    expect(call(0x12345678,0,&node)==0,"production hook removal preserves existing hook");
    marker_list.reset();marker.reset();expect(call(0x12345678,0,&node)==0,"both hook removals restore baseline");
    marker=safetyhook::create_inline(reinterpret_cast<void*>(&target),reinterpret_cast<void*>(&existing_marker));
    marker_list=safetyhook::create_inline(reinterpret_cast<void*>(&list_target),reinterpret_cast<void*>(&existing_list));
    expect(static_cast<bool>(marker)&&static_cast<bool>(marker_list),"fallback fixture has original Marker hooks");
    BYTE before[5];memcpy(before,reinterpret_cast<void*>(&target),5);
    expect(ds2fix_test_attach_fallback(reinterpret_cast<void*>(&target),reinterpret_cast<void*>(&list_target),1,true),"validated callback fallback attaches when entry route is unavailable");
    expect(memcmp(before,reinterpret_cast<void*>(&target),5)==0,"fallback does not replace original game entry hook");
    node.skip=0;entitlement=true;
    expect(call(0x12345678,0,&node)==10000 && node.skip==0,"fallback offers node and restores flag");
    ds2fix_test_mode(1,false);expect(call(0x12345678,0,&node)==0,"fallback leaves base campaign gated");
    ds2fix_test_mode(1,true);entitlement=false;expect(call(0x12345678,0,&node)==-7,"fallback preserves entitlement rejection");entitlement=true;
    expect(raw_call(0x12345678,0,&node)==0,"fallback remains limited to list construction");
    ds2fix_test_reset();expect(call(0x12345678,0,&node)==0,"fallback removal preserves Marker hooks");
    marker_list.reset();marker.reset();expect(call(0x12345678,0,&node)==0,"fallback fixture restores baseline");
    printf("PASS %u checks; actual x86 production hook, existing-hook chain, policy, restoration and price/entitlement preservation\n",checks);
}
