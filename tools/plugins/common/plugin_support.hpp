#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cwchar>
#include <mutex>
namespace plugin_support {
static bool readable(const void* p,size_t size) {
 MEMORY_BASIC_INFORMATION m{};if(!p||!VirtualQuery(p,&m,sizeof(m))||m.State!=MEM_COMMIT||(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
 uintptr_t a=reinterpret_cast<uintptr_t>(p),end=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;return a<=end&&size<=end-a;
}
static BYTE* scan_bytes(BYTE* base,size_t size,const char* signature) {
 BYTE bytes[256]{},mask[256]{};unsigned length=0;
 for(const char* p=signature;*p;){if(*p==' '){++p;continue;}if(length>=256||!p[1])return nullptr;if(p[0]=='?'&&p[1]=='?'){length++;p+=2;continue;}unsigned v=0;if(sscanf_s(p,"%2x",&v)!=1)return nullptr;bytes[length]=BYTE(v);mask[length++]=1;p+=2;}
 if(size<length)return nullptr;BYTE* hit=nullptr;
 for(size_t at=0;at<=size-length;++at){if(base[at]!=bytes[0])continue;unsigned n=1;for(;n<length&&(!mask[n]||base[at+n]==bytes[n]);++n){}if(n==length){if(hit)return nullptr;hit=base+at;}}
 return hit;
}
static BYTE* scan_game(const char* signature) {
 BYTE* base=reinterpret_cast<BYTE*>(GetModuleHandleW(nullptr));if(!readable(base,sizeof(IMAGE_DOS_HEADER)))return nullptr;
 auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);if(dos->e_magic!=IMAGE_DOS_SIGNATURE||dos->e_lfanew<=0||dos->e_lfanew>1024*1024)return nullptr;
 auto* nt=reinterpret_cast<IMAGE_NT_HEADERS*>(base+dos->e_lfanew);if(!readable(nt,sizeof(*nt))||nt->Signature!=IMAGE_NT_SIGNATURE||nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386||!nt->FileHeader.NumberOfSections)return nullptr;
 auto* section=IMAGE_FIRST_SECTION(nt);if(!readable(section,sizeof(*section)))return nullptr;size_t count=section->Misc.VirtualSize;
 if(section->VirtualAddress>=nt->OptionalHeader.SizeOfImage||count>nt->OptionalHeader.SizeOfImage-section->VirtualAddress||!readable(base+section->VirtualAddress,count))return nullptr;
 return scan_bytes(base+section->VirtualAddress,count,signature);
}
static bool known_combined_loaded() {
 if(GetModuleHandleW(L"SeveredExtras.asi"))return true;
 HMODULE module=GetModuleHandleW(L"SeveredPC.asi");if(!module)return false;wchar_t path[MAX_PATH]{};if(!GetModuleFileNameW(module,path,MAX_PATH))return false;
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);if(file==INVALID_HANDLE_VALUE)return false;
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;BYTE buffer[8192],digest[32];DWORD count=0,bytes=32;bool ok=CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&CryptCreateHash(provider,CALG_SHA_256,0,0,&hash);size_t total=0;
 while(ok){if(!ReadFile(file,buffer,sizeof(buffer),&count,nullptr)){ok=false;break;}if(!count)break;total+=count;if(total>4*1024*1024){ok=false;break;}ok=CryptHashData(hash,buffer,count,0)!=0;}
 if(ok)ok=CryptGetHashParam(hash,HP_HASHVAL,digest,&bytes,0)!=0;if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);CloseHandle(file);if(!ok)return false;
 char hex[65]{};for(unsigned i=0;i<32;i++)sprintf_s(hex+i*2,3,"%02x",digest[i]);
 const char* old[]={"fec3972b90bc48a41f854fcc783b9f18e580ff6c332f32776d6e77c07ab52fd5","bee028e9b49fb9bd0a73042f99c97d4ea4b8222be32bfdcba388a5fbbaa301a5","68a6e822ba54da3b248fb882ce121d712143644ed396f63b14bffe46f0aaad8a","02ca50558e5f2cbe6fd1c7c6fcc153869ad8b4efd261a9771eff746698569603","b0738f7c3fcb299991f96dacb04625c9185a76abd483d97c9783d6b011a3ed21","44825f30ded51c224e79371d04807432e5896315e372e6da35fbf613f5f2b716","cbc5d2a6a0eb28353e2af8c833469cd238de74a3535906501e77f235eafea475","62e35b4d9187b5e4a96ee1290db2f79d50c39998a2563eb2b5bab0080ac1a66c"};for(const char* value:old)if(!strcmp(hex,value))return true;return false;
}

static bool own_path(const void* function,const wchar_t* filename,wchar_t* output,size_t capacity) {
 HMODULE own=nullptr;if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(function),&own))return false;
 DWORD n=GetModuleFileNameW(own,output,DWORD(capacity));if(!n||n>=capacity)return false;wchar_t* slash=wcsrchr(output,wchar_t(92));if(!slash||size_t(slash+1-output)+wcslen(filename)+1>capacity)return false;
 return wcscpy_s(slash+1,capacity-size_t(slash+1-output),filename)==0;
}
static bool game_host(){wchar_t exe[MAX_PATH]{};if(!GetModuleFileNameW(nullptr,exe,MAX_PATH))return false;const wchar_t* p=wcsrchr(exe,wchar_t(92));return !_wcsicmp(p?p+1:exe,L"deadspace2.exe");}
struct Log {
 HANDLE file=INVALID_HANDLE_VALUE;std::mutex guard;
 void open(const void* function,const wchar_t* filename){wchar_t path[MAX_PATH]{};if(own_path(function,filename,path,MAX_PATH))file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);}
 void write(const char* text){if(file==INVALID_HANDLE_VALUE)return;std::lock_guard lock(guard);char b[640];int n=_snprintf_s(b,sizeof(b),_TRUNCATE,"%10lu [%lu] %s\r\n",GetTickCount(),GetCurrentThreadId(),text);if(n>0){DWORD done;WriteFile(file,b,n,&done,nullptr);}}
};

// Each ASI contains its own statically linked hook library. Serialize their
// patch attachment in this process, without importing either peer module.
class PatchGuard {
 HANDLE mutex=nullptr;bool acquired=false;
public:
 explicit PatchGuard(DWORD timeout=10000){wchar_t name[96]{};swprintf_s(name,96,L"Local%cDS2StandalonePlugins.Patch.%lu",92,GetCurrentProcessId());mutex=CreateMutexW(nullptr,FALSE,name);if(mutex){DWORD result=WaitForSingleObject(mutex,timeout);acquired=result==WAIT_OBJECT_0||result==WAIT_ABANDONED;}}
 ~PatchGuard(){if(acquired)ReleaseMutex(mutex);if(mutex)CloseHandle(mutex);}
 bool ready()const{return acquired;}
 PatchGuard(const PatchGuard&)=delete;PatchGuard& operator=(const PatchGuard&)=delete;
};
}
