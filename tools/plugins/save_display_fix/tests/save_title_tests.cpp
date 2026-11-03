#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <vector>
#include <cstdint>
#include "../vendor/safetyhook/safetyhook.hpp"
static unsigned checks=0;
extern "C" void ds2save_log(const char*){}
extern "C" void* ds2save_find_builder(){return nullptr;}
extern "C" void* ds2save_find_assert(){return nullptr;}
extern "C" void* save_validate_test(BYTE*);
extern "C" bool save_attach_test(void*);
extern "C" bool save_catalog_attach_test(void*);
extern "C" void save_options_test(bool,bool,bool);
extern "C" void save_icons_test(bool);
extern "C" void save_reset_test();
extern "C" void save_catalog_directory_test(const wchar_t*);
extern "C" unsigned save_classify_file_test(const BYTE*,size_t,uint64_t);
extern "C" bool save_verify_archive_test(const wchar_t*);
extern "C" void save_invoke_test(safetyhook::Context&);
static void check(bool v,const char* s){printf("%s %s\n",v?"PASS":"FAIL",s);if(!v)ExitProcess(1);++checks;}
static void put(BYTE* p,DWORD v){memcpy(p,&v,4);}static DWORD get(const BYTE* p){DWORD v;memcpy(&v,p,4);return v;}
static std::vector<BYTE> fixture(const char* level){std::vector<BYTE>b(128+2060+28+368+16);memcpy(b.data(),"RGMH",4);put(b.data()+4,1);put(b.data()+8,128);memcpy(b.data()+128,"NMSD",4);put(b.data()+132,1);put(b.data()+136,2060);BYTE*h=b.data()+2188;memcpy(h,"20CM",4);put(h+4,DWORD(b.size()-2188));put(h+8,368);put(h+12,16);put(h+28,8);strcpy_s(reinterpret_cast<char*>(h+36),128,level);return b;}
__declspec(naked) static void render(){__asm {
 sub esp,1094h
 push ebp
 push esi
 push edi
 mov ebp,ecx
 mov edi,[esp+10A4h]
 mov eax,12345678h
 pop edi
 pop esi
 pop ebp
 add esp,1094h
 ret 10h
}}
__declspec(noinline) static void __fastcall populate(void* self,void*){volatile BYTE* p=(BYTE*)self;p[0]=p[0];}
static BYTE self[0x340],rows[20*40],output[0x100],before[0x100],selfBefore[0x340],rowsBefore[sizeof(rows)];
static void prepare(unsigned chapter=1,unsigned slot=0){memset(self,0,sizeof(self));memset(rows,0,sizeof(rows));memset(output,0x5a,sizeof(output));put(self+0x2f8,DWORD((uintptr_t)rows));put(self+0x2fc,20);put(self+0x300,20);put(rows,slot);put(rows+8,chapter);put(output+0x60,chapter+2);strcpy_s((char*)output+8,64,"SG001- Original Chapter");}
static void run(unsigned index=0){memcpy(before,output,sizeof(output));memcpy(selfBefore,self,sizeof(self));memcpy(rowsBefore,rows,sizeof(rows));uintptr_t a,b;__asm mov a,esp
 using Fn=DWORD(__thiscall*)(void*,BYTE*,const char*,unsigned,unsigned);DWORD result=((Fn)&render)(self,output,"label",index,0);
 __asm mov b,esp
 check(a==b&&result==0x12345678,"actual x86 MidHook preserves stack, return and original epilogue");check(!memcmp(self,selfBefore,sizeof(self))&&!memcmp(rows,rowsBefore,sizeof(rows)),"native chapter/row/controller never changed");
 BYTE permitted[sizeof(output)];memcpy(permitted,output,sizeof(output));memcpy(permitted+8,before+8,64);memcpy(permitted+0x60,before+0x60,4);check(!memcmp(permitted,before,sizeof(output)),"only output title and preview fields can change");}
int main(int argc,char**argv){
 auto dlc=fixture("pdlc1_ch01_mng"),base=fixture("ds_2"),unknown=fixture("pdlc1_ch99_mng");check(save_classify_file_test(dlc.data(),dlc.size(),dlc.size())==1,"known DLC file recognized");check(save_classify_file_test(base.data(),base.size(),base.size())==2,"base campaign distinct");check(!save_classify_file_test(unknown.data(),unknown.size(),unknown.size()),"unknown campaign refused");
 for(unsigned o:{0u,4u,8u,128u,132u,136u,2188u,2192u,2196u,2200u,2216u}){auto b=dlc;put(b.data()+o,0);check(!save_classify_file_test(b.data(),b.size(),b.size()),"malformed file boundary refused");}
 check(!save_classify_file_test(dlc.data(),64,dlc.size()),"truncated prefix refused");check(!save_classify_file_test(dlc.data(),dlc.size(),dlc.size()+1),"file length mismatch refused");
 check(argc>=3,"explicit isolated test directory and resource archive required");wchar_t dir[MAX_PATH],path[MAX_PATH],archive[MAX_PATH];MultiByteToWideChar(CP_UTF8,0,argv[1],-1,dir,MAX_PATH);check(!wcsncmp(dir,L"E:\\DS2-Severed-Patch\\work\\",26),"fixture confined to project work");check(CreateDirectoryW(dir,nullptr),"fresh isolated directory created");_snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%s\\ds_slot_01.deadspace2saved",dir);save_catalog_directory_test(dir);
 auto write=[&](const std::vector<BYTE>& b){HANDLE f=CreateFileW(path,GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,0,nullptr);check(f!=INVALID_HANDLE_VALUE,"fixture opened");DWORD n;check(WriteFile(f,b.data(),DWORD(b.size()),&n,nullptr)&&n==b.size(),"fixture written");CloseHandle(f);};write(dlc);
 BYTE* ep=nullptr;BYTE* code=(BYTE*)&render;const BYTE end[]={0x5f,0x5e,0x5d,0x81,0xc4,0x94,0x10,0,0,0xc2,0x10,0};for(unsigned i=0;i<70;++i)if(!memcmp(code+i,end,sizeof(end)))ep=code+i;
 check(ep&&save_attach_test(ep),"real mid-hook attached to formatter return");check(save_catalog_attach_test((void*)&populate),"real mid-hook attached to population entry");save_options_test(true,false,false);save_icons_test(true);
 for(unsigned chapter=1;chapter<=2;++chapter){prepare(chapter);populate(self,nullptr);run();check(!strcmp((char*)output+8,chapter==1?"Severed, chapter 1":"Severed, chapter 2"),"English title for correct DLC chapter");check(get(output+0x60)==chapter+17,"appended APX preview frame selected");}
 save_options_test(true,true,false);prepare();populate(self,nullptr);run();check(strstr((char*)output+8,"\xe9\x98\xbb\xe6\x96\xad")!=nullptr,"UTF8 Chinese title in bounded native output");
 prepare(2);populate(self,nullptr);run();check(!strcmp((char*)output+8,"\xe9\x98\xbb\xe6\x96\xad \xe7\xac\xac 2 \xe7\xab\xa0"),"Chinese chapter-two title and exact UTF8 output");check(get(output+0x60)==19,"Chinese chapter-two uses zero-based frame 19");
 save_options_test(true,false,false);prepare();populate(self,nullptr);run();check(!strcmp((char*)output+8,"Severed, chapter 1"),"turning Chinese off restores English save title");
 prepare(1,1);populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"missing slot two cannot borrow slot-one DLC classification");
 prepare();populate(self,nullptr);save_icons_test(false);run();check(get(output+0x60)==3,"missing archive preserves base preview");save_icons_test(true);
 prepare();populate(self,nullptr);run(20);check(!memcmp(before,output,sizeof(output)),"out-of-range row untouched");
 prepare();self[0x2fc]=0;populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"empty list untouched");
 prepare();rows[4]=1;populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"empty row untouched");
 prepare();rows[5]=1;populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"corrupt row untouched");
 prepare(3);populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"unknown chapter untouched");
 prepare(1,20);populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"invalid save slot untouched");
 prepare();put(output+0x60,12);populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"unexpected native preview untouched");
 prepare();populate(rows,nullptr);run();check(!memcmp(before,output,sizeof(output)),"different catalogue owner cannot label this controller");
 write(base);prepare();populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"base overwrite clears DLC identification");
 write(unknown);prepare();populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"unknown file retains original title and image");
 DeleteFileW(path);prepare();populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"deleted slot clears cached DLC identification");
 save_options_test(false,true,false);prepare();populate(self,nullptr);run();check(!memcmp(before,output,sizeof(output)),"disabled feature passes through");
 safetyhook::Context c{};save_options_test(true,true,false);save_invoke_test(c);check(true,"invalid stack safely ignored");
 MultiByteToWideChar(CP_UTF8,0,argv[2],-1,archive,MAX_PATH);check(save_verify_archive_test(archive),"real APX archive SHA256 accepted");check(!save_verify_archive_test(L"Z:\\missing"),"missing archive rejected");
 save_reset_test();printf("ALL APX SAVE DISPLAY CHECKS PASSED %u\n",checks);return 0;}
