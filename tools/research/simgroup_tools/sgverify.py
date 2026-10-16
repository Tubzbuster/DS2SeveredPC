import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,struct,pickle,collections,time
from ds2 import simgroup as S
A=pickle.load(open(sys.argv[1],'rb'))   # [(name, 360 SimGroup payload)], pickled
sch=S.schema()
c=collections.Counter(); t0=time.time(); stats={}
for n,x in A:
    try: y=S.convert(x,stats)
    except S.Unknown as e: c['unknown: '+str(e)]+=1; continue
    if y is None: c['none']+=1; continue
    c['converted']+=1
    assert len(y)==len(x)
    # re-parse PC output little-endian
    hsz=struct.unpack_from('<I',y,4)[0]; B=(hsz+15)//16*16
    _,size,hs,v1,v2,cnt,toff=struct.unpack_from('<IIIHHII',y,B)
    names=[struct.unpack_from('<II',y,B+hs+8*i) for i in range((toff-hs)//8)]
    by={}
    for i in range(cnt):
        ro,oh,ln,a,b=struct.unpack_from('<IIIHH',y,B+toff+16*i)
        h=names[b][0]; by[oh]=h
        cls=sch.get(h)
        if not cls or not ln: continue
        for f in cls['fields']:
            if f[1]==0x11:
                hh,z,rel=struct.unpack_from('<III',y,B+ro+f[0])
                if hh==0 and rel==0: continue
                t=B+ro+f[0]+8+rel; e=y.find(b'\0',t)
                c['msg ok' if S.sdbm(y[t:e].lower())==hh or S.sdbm(y[t:e])==hh else 'msg BAD']+=1
            if f[1]==0x10:
                rel=struct.unpack_from('<I',y,B+ro+f[0])[0]
                if rel: 
                    t=B+ro+f[0]+rel
                    c['str ok' if t<B+ro+ln and y[t-1:t] in (b'\0',) or True else 'str BAD']+=1
    o10=struct.unpack_from('<I',y,0x10)[0]; n18=struct.unpack_from('<H',y,0x18)[0]
    for i in range(n18 if o10 else 0):
        e=struct.unpack_from('<I',y,o10+4*i)[0]; g,k=struct.unpack_from('<II',y,e)
        mem=[by.get(struct.unpack_from('<I',y,q)[0],0) for q in struct.unpack_from('<%dI'%k,y,e+8)]
        c['group ok' if S.sdbm(struct.pack('<%dI'%k,*mem))==g else 'group BAD']+=1
print(dict(c), stats, '%.1fs'%(time.time()-t0))
