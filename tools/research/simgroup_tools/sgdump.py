import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,os,struct,re,json
from ds2 import streamfile, simgroup
sch=simgroup.schema()
def dump(x):
    hsz=struct.unpack_from('>I',x,4)[0]; B=(hsz+15)//16*16
    if struct.unpack_from('>I',x,B)[0]!=simgroup.BLOCK: return
    _,size,hs,v1,v2,cnt,toff=struct.unpack_from('>IIIHHII',x,B)
    names=[struct.unpack_from('>II',x,B+hs+8*i) for i in range((toff-hs)//8)]
    for i in range(cnt):
        ro,oh,ln,a,b=struct.unpack_from('>IIIHH',x,B+toff+16*i)
        h=names[b][0] if b<len(names) else 0
        cn=sch[h]['name'] if h in sch else simgroup.REMAP.get(h,'?%08X'%h)
        rec=x[B+ro:B+ro+ln]
        strs=[s.decode() for s in re.findall(rb'[A-Za-z0-9_ .\\/:\-]{3,}',rec)]
        yield i,oh,cn,ln,strs,rec
if __name__=='__main__':
    for path in sys.argv[1:]:
        for a in streamfile.read(open(path,'rb').read())[1]:
            if a.type!='SimGroup': continue
            for i,oh,cn,ln,strs,rec in dump(a.payload()):
                print('%s|%s|%08X|%s|%d|%s'%(os.path.basename(path),a.name,oh,cn,ln,' ; '.join(strs)))
