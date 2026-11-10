#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
int main(int n,char**a){if(n<2||GetModuleHandleW(L"SeveredPC.asi"))return 1;for(int i=1;i<n;++i){if(!LoadLibraryA(a[i])){printf("FAIL load %s code=%lu\n",a[i],GetLastError());return 1;}if(GetModuleHandleW(L"SeveredPC.asi")){puts("FAIL unexpected core import");return 1;}}puts("PASS both standalone ASIs load together without SeveredPC; non-game host remains inactive");return 0;}
