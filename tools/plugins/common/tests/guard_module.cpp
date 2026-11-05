#include "../plugin_support.hpp"
static volatile LONG active=0;
extern "C" int __cdecl TryGuard(DWORD wait,DWORD hold){plugin_support::PatchGuard guard(wait);if(!guard.ready())return 0;InterlockedExchange(&active,1);if(hold)Sleep(hold);InterlockedExchange(&active,0);return 1;}
extern "C" int __cdecl IsActive(){return InterlockedCompareExchange(&active,0,0);}
#pragma comment(linker,"/EXPORT:TryGuard=_TryGuard")
#pragma comment(linker,"/EXPORT:IsActive=_IsActive")
