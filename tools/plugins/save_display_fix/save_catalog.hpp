#pragma once
#include <windows.h>
#include <shlobj.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cwchar>
namespace severed_saves {
constexpr size_t kPrefixLimit=65536,kMaximumName=31;
struct Snapshot { uintptr_t owner=0;unsigned kinds[20]{}; };
inline thread_local Snapshot current{};
inline wchar_t directory[MAX_PATH]{};
inline DWORD dword(const BYTE* p){DWORD value;memcpy(&value,p,4);return value;}
// Known RGMH v1 -> NMSD v1 -> one MC02 container. Only read metadata;
// the three opaque MC02 words are not treated as validated checksums.
inline unsigned classify(const BYTE* data,size_t prefix,uint64_t fileBytes) {
 if(!data||prefix<40||memcmp(data,"RGMH",4)||dword(data+4)!=1)return 0;
 uint64_t outer=dword(data+8);if(outer<40||outer>prefix||prefix-outer<12)return 0;
 const BYTE* n=data+size_t(outer);if(memcmp(n,"NMSD",4)||dword(n+4)!=1)return 0;
 uint64_t chunk=dword(n+8);if(chunk<12)return 0;uint64_t at=outer+chunk;
 if(at>prefix||prefix-at<28+368||at>fileBytes||memcmp(data+at,"20CM",4))return 0;
 const BYTE* h=data+size_t(at);uint64_t total=dword(h+4),meta=dword(h+8),body=dword(h+12);
 if(meta!=368||total!=fileBytes-at||total!=28+meta+body||dword(h+28)!=8)return 0;
 const char* level=reinterpret_cast<const char*>(h+28+8);size_t length=0;
 for(;length<128&&level[length];++length){char c=level[length];if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'))return 0;}
 if(length==128||length<4)return 0;
 return !strcmp(level,"pdlc1_ch01_mng")?1:!strcmp(level,"ds_2")?2:0;
}
inline bool initialise() {
 wchar_t documents[MAX_PATH]{};
 if(FAILED(SHGetFolderPathW(nullptr,CSIDL_PERSONAL,nullptr,SHGFP_TYPE_CURRENT,documents)))return false;
 return _snwprintf_s(directory,MAX_PATH,_TRUNCATE,L"%s\\EA Games\\Dead Space 2",documents)>0;
}
inline bool equal_info(const BY_HANDLE_FILE_INFORMATION& a,const BY_HANDLE_FILE_INFORMATION& b) {
 return a.dwVolumeSerialNumber==b.dwVolumeSerialNumber&&a.nFileIndexHigh==b.nFileIndexHigh&&a.nFileIndexLow==b.nFileIndexLow&&a.nFileSizeHigh==b.nFileSizeHigh&&a.nFileSizeLow==b.nFileSizeLow&&CompareFileTime(&a.ftLastWriteTime,&b.ftLastWriteTime)==0;
}
inline unsigned read_slot(unsigned slot) {
 if(slot<1||slot>20||!directory[0])return 0;
 wchar_t path[MAX_PATH]{};if(_snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%s\\ds_slot_%02u.deadspace2saved",directory,slot)<0)return 0;
 // Sharing permits the game and cloud sync to operate normally. A changed
 // size/mtime/file identity causes the result to be discarded.
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 if(file==INVALID_HANDLE_VALUE)return 0;
 BY_HANDLE_FILE_INFORMATION before{},after{};unsigned result=0;
 if(GetFileInformationByHandle(file,&before)&&before.nFileSizeHigh==0&&before.nFileSizeLow>=40&&!(before.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))) {
  BYTE data[kPrefixLimit];DWORD wanted=before.nFileSizeLow<kPrefixLimit?before.nFileSizeLow:DWORD(kPrefixLimit),done=0;
  while(done<wanted){DWORD read=0;if(!ReadFile(file,data+done,wanted-done,&read,nullptr)||!read)break;done+=read;}
  if(done==wanted&&GetFileInformationByHandle(file,&after)&&equal_info(before,after))result=classify(data,done,before.nFileSizeLow);
 }
 CloseHandle(file);return result;
}
inline void refresh(uintptr_t owner) {
 Snapshot next{};next.owner=owner;
 for(unsigned slot=1;slot<=20;++slot)next.kinds[slot-1]=read_slot(slot);
 current=next;
}
inline unsigned match(const BYTE* row,size_t bytes,unsigned slot) {
 if(!row||bytes<2*kMaximumName||slot<1||slot>20||!current.owner)return 0;
 uintptr_t offset=0x64A00-0x448+(slot-1)*0x470;
 if(current.owner>UINTPTR_MAX-offset||reinterpret_cast<uintptr_t>(row)!=current.owner+offset)return 0;
 wchar_t expected[kMaximumName]{};_snwprintf_s(expected,kMaximumName,_TRUNCATE,L"ds_slot_%02u.deadspace2saved",slot);
 wchar_t filename[kMaximumName]{};memcpy(filename,row,sizeof(filename));
 if(wcsnlen_s(filename,kMaximumName)==kMaximumName||_wcsicmp(filename,expected))return 0;
 return current.kinds[slot-1];
}
}
