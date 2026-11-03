#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <atomic>
#include <mutex>
#include "safetyhook/safetyhook.hpp"
#include "store_policy.hpp"

// Optional Severed Power Node shop fix. Based on MarkerPatch's existing
// chapter/round bypass mechanism; the temporary field is restored after use.
static safetyhook::InlineHook g_shop;
static safetyhook::InlineHook g_store_list;
static thread_local unsigned g_list_depth=0;
static std::atomic_bool g_severed{false};
static std::atomic_int g_profile{0};
static std::atomic<HANDLE> g_diag{INVALID_HANDLE_VALUE};
static std::mutex g_log_mutex;
static bool readable(const void* p,size_t len) {
    MEMORY_BASIC_INFORMATION mi{};
    if(!p || !VirtualQuery(p,&mi,sizeof(mi)) || mi.State!=MEM_COMMIT || (mi.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
    const uintptr_t a=reinterpret_cast<uintptr_t>(p),end=reinterpret_cast<uintptr_t>(mi.BaseAddress)+mi.RegionSize;
    return a<=end && len<=end-a;
}
static bool writable(const void* p,size_t len) {
    MEMORY_BASIC_INFORMATION mi{};
    if(!readable(p,len) || !VirtualQuery(p,&mi,sizeof(mi)))return false;
    return (mi.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))!=0;
}
static void line(const char* text) {
    HANDLE file=g_diag.load(std::memory_order_acquire);
    if(file==INVALID_HANDLE_VALUE)return;
    std::lock_guard lock(g_log_mutex);
    char b[640];int n=_snprintf_s(b,sizeof(b),_TRUNCATE,"%10lu [%lu] %s\r\n",GetTickCount(),GetCurrentThreadId(),text);
    if(n>0){DWORD written=0;WriteFile(file,b,static_cast<DWORD>(n),&written,nullptr);}
}
static bool build_date(uintptr_t base,size_t image,DWORD raw,const char* date) {
    const uintptr_t rva=raw-0x400000;const size_t n=strlen(date)+1;
    if(rva>image || n>image-rva)return false;
    const void* p=reinterpret_cast<const void*>(base+rva);
    return readable(p,n) && memcmp(p,date,n)==0;
}
static void* existing_jump_target(void* target) {
    auto cursor=reinterpret_cast<uintptr_t>(target);
    bool followed=false;
    // SafetyHook x86 jumps via an allocated relay, then into the owning DLL.
    // Resolve that real chain rather than expecting the first JMP to hit it.
    for(unsigned hops=0;hops<8;++hops) {
        const auto* p=reinterpret_cast<const BYTE*>(cursor);
        MEMORY_BASIC_INFORMATION mi{};
        if(!readable(p,5) || !VirtualQuery(p,&mi,sizeof(mi)) || !(mi.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)))return nullptr;
        if(p[0]!=0xE9) {
            HMODULE owner=nullptr;
            if(followed && GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(cursor),&owner))return reinterpret_cast<void*>(cursor);
            return nullptr;
        }
        followed=true;cursor+=5+*reinterpret_cast<const int32_t*>(p+1);
    }
    return nullptr;
}

static HMODULE existing_jump_owner(void* target) {
    void* resolved=existing_jump_target(target);HMODULE owner=nullptr;
    if(resolved)GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(resolved),&owner);
    return owner;
}

static int __fastcall shop_hook(int self,int,ds2fix::Guid* entry) {
    if(!readable(entry,0x1a))return g_shop.thiscall<int>(self,entry);
    const ds2fix::Guid guid=*entry;
    auto* flag=reinterpret_cast<BYTE*>(entry)+0x19;
    const BYTE old=*flag;
    const bool active=g_severed.load(std::memory_order_relaxed);
    const int profile=g_profile.load(std::memory_order_relaxed);
    const bool apply=g_list_depth>0 && ds2fix::permitted(guid,profile,active) && old<=1 && writable(flag,1);
    if(apply)*flag=1;
    int result;
    // Restore the temporary input even if the game raises a Windows exception.
    __try { result=g_shop.thiscall<int>(self,entry); }
    __finally { if(apply)*flag=old; }
    if(apply) {
        char b[512];_snprintf_s(b,sizeof(b),_TRUNCATE,
            "SHOP guid=%08lX-%08lX-%08lX-%08lX profile=%d bypass=%d old=%u restored=%u result=%d",
            guid.words[0],guid.words[1],guid.words[2],guid.words[3],profile,apply?1:0,old,*flag,result);
        line(b);
    }
    return result;
}
static void __fastcall store_list_hook(int self,int) {
    ++g_list_depth;
    __try { g_store_list.thiscall<void>(self); }
    __finally { --g_list_depth; }
}

extern "C" void ds2fix_campaign(int active) {
    g_severed.store(active!=0,std::memory_order_relaxed);
}

static bool attach_one(void* address,void* detour,safetyhook::InlineHook& hook,const char* stage) {
    auto result=safetyhook::InlineHook::create(address,detour);
    if(!result){
        const auto error=result.error();char b[240];
        if(error.type==safetyhook::InlineHook::Error::BAD_ALLOCATION)
            _snprintf_s(b,sizeof(b),_TRUNCATE,"HOOK FAILED stage=%s type=%u allocation=%u",stage,static_cast<unsigned>(error.type),static_cast<unsigned>(error.allocator_error));
        else _snprintf_s(b,sizeof(b),_TRUNCATE,"HOOK FAILED stage=%s type=%u instruction=%p",stage,static_cast<unsigned>(error.type),error.ip);
        line(b);return false;
    }
    hook=std::move(*result);return true;
}
static bool attach_pair(void* target,void* list_target,bool force_fallback=false) {
    if(!force_fallback && attach_one(target,reinterpret_cast<void*>(shop_hook),g_shop,"entry.item") &&
       attach_one(list_target,reinterpret_cast<void*>(store_list_hook),g_store_list,"entry.list")){
        line("HOOK ROUTE game-entry chain");return true;
    }
    g_store_list.reset();g_shop.reset();
    // The caller has already verified both E9 chains terminate in MarkerPatch.
    // Hook those exact validated callbacks rather than guessing encrypted game prologues.
    void* item_callback=existing_jump_target(target);void* list_callback=existing_jump_target(list_target);
    if(!item_callback || !list_callback || item_callback==target || list_callback==list_target || item_callback==list_callback){
        line("FALLBACK REFUSED: callback chain unavailable");return false;
    }
    line("FALLBACK attempting validated MarkerPatch callbacks");
    if(attach_one(item_callback,reinterpret_cast<void*>(shop_hook),g_shop,"marker.item") &&
       attach_one(list_callback,reinterpret_cast<void*>(store_list_hook),g_store_list,"marker.list")){
        line("HOOK ROUTE validated MarkerPatch callbacks");return true;
    }
    g_store_list.reset();g_shop.reset();return false;
}

extern "C" void ds2fix_install(int level_hook_ready) {
    wchar_t exe[MAX_PATH]{};GetModuleFileNameW(nullptr,exe,MAX_PATH);
    const wchar_t* name=wcsrchr(exe,L'\\');name=name?name+1:exe;
    if(_wcsicmp(name,L"deadspace2.exe"))return;
    HMODULE own=nullptr;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(&ds2fix_install),&own))return;
    wchar_t dir[MAX_PATH]{};GetModuleFileNameW(own,dir,MAX_PATH);wchar_t* slash=wcsrchr(dir,L'\\');if(!slash)return;slash[1]=0;
    wchar_t ini[MAX_PATH]{},log[MAX_PATH]{};
    _snwprintf_s(ini,MAX_PATH,_TRUNCATE,L"%sSeveredNodeFix.ini",dir);
    if(GetPrivateProfileIntW(L"Shop",L"EnablePowerNodeShopFix",0,ini)!=1)return;
    _snwprintf_s(log,MAX_PATH,_TRUNCATE,L"%sSeveredPowerNodeFix.log",dir);
    g_diag.store(CreateFileW(log,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr),std::memory_order_release);
    g_profile.store(1,std::memory_order_relaxed);
    line("Optional Severed Power Node fix enabled; MarkerPatch shop hooks required");
    if(!level_hook_ready){line("DISABLED: Severed level observer unavailable");return;}
    auto base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    auto dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    auto nt=reinterpret_cast<IMAGE_NT_HEADERS*>(base+dos->e_lfanew);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386){line("DISABLED: unsupported image");return;}
    const size_t image=nt->OptionalHeader.SizeOfImage;
    if(!build_date(base,image,0x1B92078,"Feb 24 2011") && !build_date(base,image,0x1B92078,"Feb 16 2011")){
        line("DISABLED: unsupported game build (only current/1.1 address layout)");return;
    }
    // Address and entry flag are from MarkerPatch's audited BonusUnlocks hook.
    // SafetyHook relocates an existing relative JMP if MarkerPatch hooked first.
    void* target=reinterpret_cast<void*>(base+(0xBB5920-0x400000));
    void* list_target=reinterpret_cast<void*>(base+(0xEA0050-0x400000));
    auto known_marker_hook=[](void* address) {
    // This optional integration requires the known MarkerPatch hook rather than
    // patching possibly still-encrypted DRM bytes or an unknown mod's jump.
    HMODULE owner=existing_jump_owner(address);wchar_t owner_path[MAX_PATH]{};
    if(!owner || !GetModuleFileNameW(owner,owner_path,MAX_PATH)){
        return false;
    }
    const wchar_t* owner_name=wcsrchr(owner_path,L'\\');owner_name=owner_name?owner_name+1:owner_path;
    if(_wcsicmp(owner_name,L"dinput8.dll") && _wcsicmp(owner_name,L"MarkerPatch.asi")){
        return false;
    }
    return true;
    };
    if(!known_marker_hook(target) || !known_marker_hook(list_target)){
        line("DISABLED: known MarkerPatch shop hooks missing (node fix requires EnableHackerDLC=1)");return;
    }
    if(!attach_pair(target,list_target)){line("DISABLED: store/list hook failed after validated fallback");return;}
    line("STORE HOOK READY (Severed node only; store-list scope; original price and entitlements retained)");
}

#ifdef DS2FIX_TEST
extern "C" bool ds2fix_test_attach(void* address,void* list_address,int profile,bool active) {
    g_profile.store(profile);g_severed.store(active);
    return attach_pair(address,list_address);
}
extern "C" bool ds2fix_test_attach_fallback(void* address,void* list_address,int profile,bool active) {
    g_profile.store(profile);g_severed.store(active);return attach_pair(address,list_address,true);
}
extern "C" void ds2fix_test_mode(int profile,bool active) {g_profile.store(profile);g_severed.store(active);}
extern "C" void ds2fix_test_reset() {g_store_list.reset();g_shop.reset();}
extern "C" bool ds2fix_test_jump_owner(void* address,HMODULE owner) {return existing_jump_owner(address)==owner;}
#endif
