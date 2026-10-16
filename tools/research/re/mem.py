from hkc import *
def mems(addr,n):
    out=[]
    for i in range(n):
        f=v2f(addr+24*i)
        nm,cl,en,ty,st,ca,fl,off,at=struct.unpack_from('<IIIBBhHHI',d,f)
        out.append((cstr(nm),ty,st,ca,fl,off, cl and hex(cl), en and hex(en)))
    return out
import sys
for n in sys.argv[1:]:
    cls,vals=REG[n]; print(n,hex(cls),[hex(v) if v is not None else None for v in vals])
