#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <atomic>
#include <initializer_list>
#include "save_catalog.hpp"
#include "save_icon_contract.hpp"
#include "safetyhook/safetyhook.hpp"
#include "runtime_config.hpp"
#include "../common/plugin_support.hpp"
extern "C" void ds2save_log(const char*);
extern "C" void* ds2save_find_builder();
namespace {
safetyhook::MidHook g_hook,g_builderHook,g_ingameHook,g_ingameBuilderHook;
std::atomic_bool g_nativeIcons{false};
std::atomic_bool g_enabled{false},g_chinese{false},g_trace{false},g_icons{false},g_titles{true};
std::atomic_uint g_seen[21]{};
const char* const kEnglish[]={"Severed, chapter 1","Severed, chapter 2"};
const char* const kChinese[]={"\xE9\x98\xBB\xE6\x96\xAD \xE7\xAC\xAC 1 \xE7\xAB\xA0","\xE9\x98\xBB\xE6\x96\xAD \xE7\xAC\xAC 2 \xE7\xAB\xA0"};
bool memory(const void* p,size_t len,bool write=false) {
 MEMORY_BASIC_INFORMATION q{};if(!p||!VirtualQuery(p,&q,sizeof(q))||q.State!=MEM_COMMIT||(q.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
 const uintptr_t at=reinterpret_cast<uintptr_t>(p),end=reinterpret_cast<uintptr_t>(q.BaseAddress)+static_cast<uintptr_t>(q.RegionSize);
 if(at>end||len>end-at)return false;
 return !write||(q.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY));
}
bool executable(const void* p){MEMORY_BASIC_INFORMATION q{};return memory(p,1)&&VirtualQuery(p,&q,sizeof(q))&&(q.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY));}
DWORD word(const BYTE* p){DWORD x;memcpy(&x,p,4);return x;}
void trace(unsigned slot,int chapter,unsigned reason,const char* result) {
 if(!g_trace.load()||reason>15)return;unsigned i=slot>=1&&slot<=20?slot:0,bit=1u<<reason;
 if(g_seen[i].fetch_or(bit)&bit)return;
 char line[180];_snprintf_s(line,sizeof(line),_TRUNCATE,"SAVE_APX slot=%u chapter=%d title=%d icon=%d result=%s",slot,chapter,int(g_titles.load()),int(g_icons.load()),result);ds2save_log(line);
}
bool icon_archive(const wchar_t* path,bool native=false) {
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
 if(file==INVALID_HANDLE_VALUE)return false;
 LARGE_INTEGER size{};bool ok=GetFileSizeEx(file,&size)&&(size.QuadPart==kCombinedIconArchiveBytes||(!native&&size.QuadPart==kIconArchiveBytes));
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;
 if(ok)ok=CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)!=0;
 if(ok)ok=CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)!=0;
 BYTE buffer[65536];DWORD read=0;unsigned total=0;
 while(ok&&total<static_cast<unsigned>(size.QuadPart)){ok=ReadFile(file,buffer,sizeof(buffer),&read,nullptr)&&read>0;if(ok){total+=read;ok=CryptHashData(hash,buffer,read,0)!=0;}}
 BYTE digest[32]{};DWORD length=sizeof(digest);if(ok)ok=CryptGetHashParam(hash,HP_HASHVAL,digest,&length,0)&&length==32;
 char hex[65]{};if(ok){for(unsigned i=0;i<32;++i)sprintf_s(hex+i*2,3,"%02x",digest[i]);ok=!strcmp(hex,size.QuadPart==kCombinedIconArchiveBytes?kCombinedIconArchiveSha:kIconArchiveSha);}
 if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);CloseHandle(file);return ok;
}
bool game_icons(bool native=false) {
 wchar_t path[MAX_PATH]{};if(!GetModuleFileNameW(nullptr,path,MAX_PATH))return false;
 wchar_t* name=wcsrchr(path,L'\\');if(!name||size_t(name-path)+16>=MAX_PATH)return false;
 wcscpy_s(name+1,MAX_PATH-size_t(name-path)-1,L"DS2DAT3.DAT");return icon_archive(path,native);
}

// Called at the normal return of the actual SP11SaveSlot row formatter.
// EBP is this, EDI is its output copy. The original third argument is the
// row index. These are UI buffers only: never change row.chapter or a save.
void on_row(safetyhook::Context& ctx) {
 if(!g_enabled.load())return;
 if(!memory(reinterpret_cast<void*>(ctx.esp),0x10B4)){trace(0,-1,3,"kept_stack");return;}
 auto* self=reinterpret_cast<BYTE*>(ctx.ebp);auto* output=reinterpret_cast<BYTE*>(ctx.edi);const BYTE* stack=reinterpret_cast<const BYTE*>(ctx.esp);
 if(!memory(self,0x308)||!memory(output,0xEC,true)||word(stack+0x10A4)!=ctx.edi){trace(0,-1,4,"kept_context");return;}
 unsigned index=word(stack+0x10AC),count=word(self+0x2FC),capacity=word(self+0x300);uintptr_t rows=word(self+0x2F8);
 if(index>=20||count>20||!count||index>=count||capacity<count||capacity>4096||rows>UINTPTR_MAX-index*40){trace(0,-1,5,"kept_rows");return;}
 const auto* row=reinterpret_cast<const BYTE*>(rows+index*40);
 if(!memory(row,40)||row[4]||row[5]){trace(0,-1,6,"kept_empty_corrupt");return;}
 unsigned number=word(row),chapter=word(row+8);if(number>=20||chapter<1||chapter>2){trace(number+1,int(chapter),7,"kept_chapter");return;}
 const unsigned slot=number+1;
 if(severed_saves::current.owner!=ctx.ebp||severed_saves::current.kinds[number]!=1){trace(slot,chapter,8,"kept_catalog");return;}
 // Confirm the original formatter produced the expected ordinary frame.
 if(word(output+0x60)!=chapter+2){trace(slot,chapter,9,"kept_preview_layout");return;}
 if(g_titles.load()){const char* title=(g_chinese.load()?kChinese:kEnglish)[chapter-1];strcpy_s(reinterpret_cast<char*>(output+8),64,title);}
 if(g_icons.load()){const unsigned frame=kDlcPreviewFrames[chapter-1];memcpy(output+0x60,&frame,4);}
 trace(slot,chapter,chapter,"updated_output");
}
// This uniquely identified method populates the actual 40-byte row array.
// Refresh the read-only file catalogue once here, outside the row callback.
void on_builder(safetyhook::Context& ctx){severed_saves::refresh(ctx.ecx);}
// The holographic in-game list uses a separate native serializer. At this
// site EDI addresses this slot's metadata, EBP is its 1-based slot number,
// and the stack contains only temporary title/VFX values awaiting submission.
void on_ingame_builder(safetyhook::Context& ctx){severed_saves::refresh(severed_saves::in_game,ctx.ecx);}
void on_ingame_row(safetyhook::Context& ctx) {
 if(!g_enabled.load()||ctx.ebp<1||ctx.ebp>20||ctx.edi<0x448)return;
 auto* stack=reinterpret_cast<BYTE*>(ctx.esp);auto* record=reinterpret_cast<const BYTE*>(ctx.edi);
 if(!memory(stack,0x114,true)||!stack[0x40]||!memory(record,4))return;
 const unsigned chapter=word(record);const auto* filename=record-0x448;
 if(chapter<1||chapter>2||!memory(filename,2*severed_saves::kMaximumName)||severed_saves::match(severed_saves::in_game,filename,2*severed_saves::kMaximumName,ctx.ebp)!=1)return;
 if(g_titles.load())strcpy_s(reinterpret_cast<char*>(stack+0x50),100,(g_chinese.load()?kChinese:kEnglish)[chapter-1]);
 if(g_nativeIcons.load())memcpy(stack+0x30,kNativeDlcGuids[chapter-1],16);
 trace(ctx.ebp,chapter,10+chapter,"updated_ingame_output");
}
BYTE* validated_ingame_site(BYTE* fn) {
 static const BYTE prefix[]={0x55,0x8B,0xEC,0x83,0xE4,0xF8,0x81,0xEC,0x14,0x01,0,0};
 static const BYTE rows[]={0x33,0xF6,0x8D,0xB9,0,0x4A,0x06,0};
 static const BYTE submit[]={0x8B,0x4C,0x24,0x0C,0x8D,0x54,0x24,0x18,0x52,0x8D,0x84,0x24,0xBC,0,0,0,0x50,0xE8};
 static const BYTE loop[]={0x8B,0xF5,0x81,0xC7,0x70,0x04,0,0,0x83,0xFE,0x14};
 if(!executable(fn)||!memory(fn,0x200)||memcmp(fn,prefix,sizeof(prefix))||memcmp(fn+0x18,rows,sizeof(rows))||memcmp(fn+0x186,submit,sizeof(submit))||memcmp(fn+0x19C,loop,sizeof(loop)))return nullptr;
 return fn+0x186;
}
BYTE* validated_site(BYTE* fn) {
 static const BYTE prefix[]={0xB8,0x94,0x10,0,0,0xE8};
 static const BYTE fields[]={0x8B,0x84,0x24,0xA4,0x10,0,0,0x55,0x56,0x57,0x8B,0xBC,0x24,0xA4,0x10,0,0,0x89,0x07,0x8B,0x84,0x24,0xAC,0x10,0,0};
 static const BYTE title[]={0x8D,0x47,0x08}; // More detailed checks below use invariant bytes from this binary.
 static const BYTE epilogue[]={0x5F,0x5E,0x5D,0x81,0xC4,0x94,0x10,0,0,0xC2,0x10,0};
 static const BYTE preview[]={0x83,0xC0,0x02,0x89,0x47,0x60};
 static const BYTE populate[]={0x83,0xEC,0x64,0x53,0x56,0x57,0x8B,0x3D};
 if(!executable(fn)||!memory(fn,0x3B0)||memcmp(fn,prefix,sizeof(prefix))||memcmp(fn+10,fields,sizeof(fields)))return nullptr;
 if(memcmp(fn+0x2B4,preview,sizeof(preview))||memcmp(fn+0x353,epilogue,sizeof(epilogue))||memcmp(fn+0x370,populate,sizeof(populate)))return nullptr;
 return fn+0x353;
}
bool attach(void* p){auto h=safetyhook::MidHook::create(p,on_row);if(!h)return false;g_hook=std::move(*h);return true;}
bool attach_builder(void* p){auto h=safetyhook::MidHook::create(p,on_builder);if(!h)return false;g_builderHook=std::move(*h);return true;}
DWORD WINAPI worker(void*) {
 wchar_t ini[MAX_PATH]{};if(!severed_menu_ini_path(ini,MAX_PATH))return 0;
 const bool titles=GetPrivateProfileIntW(L"SaveDisplay",L"TitleFix",0,ini)==1;bool icons=GetPrivateProfileIntW(L"SaveDisplay",L"IconFix",0,ini)==1;g_titles.store(titles);
 if(icons){g_nativeIcons.store(game_icons(true));icons=game_icons();ds2save_log(icons?"SAVE_APX_ICON verified two-chapter preview archive":"SAVE_APX_ICON archive absent or changed; original pictures retained");}g_icons.store(icons);
 if(!titles&&!icons)return 0;
 if(!severed_saves::initialise()){ds2save_log("SAVE_APX Documents unavailable; display retained");return 0;}
 g_chinese.store((GetPrivateProfileIntW(L"Localization",L"SimplifiedChinese",0,ini)==1));g_trace.store(GetPrivateProfileIntW(L"SaveDisplay",L"TraceRows",0,ini)==1);
 for(unsigned n=0;n<600;++n){auto* fn=static_cast<BYTE*>(ds2save_find_builder());if(fn){BYTE* site=validated_site(fn);if(!site){ds2save_log("SAVE_APX signature/layout unsupported; display retained");return 0;}
  plugin_support::PatchGuard guard;if(!guard.ready()){ds2save_log("SAVE_APX patch coordination unavailable; original display retained");return 0;}
  if(attach(site)&&attach_builder(fn+0x370)){g_enabled.store(true);ds2save_log("SAVE_APX actual SP11SaveSlot formatter hooked; file catalogue matches native slot; saves remain read-only");
   auto* native=plugin_support::scan_game("55 8B EC 83 E4 F8 81 EC 14 01 00 00 A1 ?? ?? ?? ?? 55 56 57 89 44 24 0C 33 F6 8D B9 00 4A 06 00");
   auto* nativeSite=validated_ingame_site(native);
   if(nativeSite){auto entry=safetyhook::MidHook::create(native,on_ingame_builder);if(entry){g_ingameBuilderHook=std::move(*entry);auto row=safetyhook::MidHook::create(nativeSite,on_ingame_row);if(row){g_ingameHook=std::move(*row);ds2save_log("SAVE_INGAME native serializer hooked; existing save metadata stays read-only");}else g_ingameBuilderHook.reset();}}
   else ds2save_log("SAVE_INGAME serializer unsupported; original in-game display retained");
  }
  else{g_hook.reset();g_builderHook.reset();ds2save_log("SAVE_APX hooks failed; display retained");}return 0;}Sleep(500);}
 ds2save_log("SAVE_APX formatter unavailable; display retained");return 0;
}
}
extern "C" void ds2save_start(){wchar_t exe[MAX_PATH]{};if(!GetModuleFileNameW(nullptr,exe,MAX_PATH))return;const wchar_t* name=wcsrchr(exe,wchar_t(92));name=name?name+1:exe;if(_wcsicmp(name,L"deadspace2.exe"))return;HANDLE t=CreateThread(nullptr,0,worker,nullptr,0,nullptr);if(t)CloseHandle(t);}
#ifdef DS2SAVE_TEST
extern "C" void* save_validate_test(BYTE* p){return validated_site(p);}
extern "C" bool save_attach_test(void* p){return attach(p);}
extern "C" bool save_catalog_attach_test(void* p){return attach_builder(p);}
extern "C" void save_options_test(bool e,bool c,bool t){g_enabled.store(e);g_chinese.store(c);g_trace.store(t);g_titles.store(true);for(auto& x:g_seen)x.store(0);}
extern "C" void save_icons_test(bool e){g_icons.store(e);}
extern "C" void save_catalog_directory_test(const wchar_t* p){wcscpy_s(severed_saves::directory,p);}
extern "C" void save_reset_test(){g_hook.reset();g_builderHook.reset();g_ingameHook.reset();g_ingameBuilderHook.reset();severed_saves::current={};severed_saves::in_game={};}
extern "C" void save_invoke_test(safetyhook::Context& c){on_row(c);}
extern "C" bool save_verify_archive_test(const wchar_t* p){return icon_archive(p);}
extern "C" unsigned save_classify_file_test(const BYTE* d,size_t n,uint64_t b){return severed_saves::classify(d,n,b);}
extern "C" void* save_ingame_validate_test(BYTE* p){return validated_ingame_site(p);}
extern "C" void save_ingame_invoke_test(safetyhook::Context& c){on_ingame_row(c);}
extern "C" void save_ingame_refresh_test(uintptr_t p){severed_saves::refresh(severed_saves::in_game,p);}
extern "C" void save_native_icons_test(bool enabled){g_nativeIcons.store(enabled);}
#endif
