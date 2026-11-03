#pragma once
#include <cstdint>
namespace ds2fix {
struct Guid { uint32_t words[4]; };
inline constexpr Guid power_node = {{0x37C7B444,0x8607BF9D,0x4E59414D,0x36445241}};
inline bool equal(const Guid& a,const Guid& b) { for(int i=0;i<4;++i)if(a.words[i]!=b.words[i])return false;return true; }
inline bool permitted(const Guid& guid,int mode,bool severed) { return severed && mode==1 && equal(guid,power_node); }
}
