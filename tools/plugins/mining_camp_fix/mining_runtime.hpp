#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
namespace mining_camp {
inline DWORD word(const BYTE* p) { DWORD v; memcpy(&v,p,4); return v; }
// TriggerAuto's base constructor copies the serialized GUID to +24h and
// its compiled parameters to +0Ch. Only this one DLC object is eligible.
inline bool matches(const BYTE* actor, const BYTE* config) {
 static constexpr DWORD guid[]={0x4FCB8B7D,0x0206C813,0x4952414D,0x4C4C454E};
 return !memcmp(actor+0x24,guid,sizeof(guid)) && word(actor+0x34)==0xEB27FF6B
     && word(config)==0x442FCCC9 && word(config+12)==0 && word(config+16)==1;
}
inline bool correct(BYTE* actor, BYTE* config) {
 if(!matches(actor,config))return false;
 const DWORD repeatable=0;memcpy(config+16,&repeatable,4);return true;
}
}
