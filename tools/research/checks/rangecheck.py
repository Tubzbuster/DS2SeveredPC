import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,struct,collections
from ds2 import streamfile, geo, build, meshconv
tm=build._model('mesh_templates.pkl')
c=collections.Counter(); ex=[]
for p in sys.argv[1:]:
    for x in streamfile.read(open(p,'rb').read())[1]:
        if x.type!='Mesh': continue
        src=x.payload(); y=meshconv.convert(src,tm); g=geo.parse(y,False)
        vbs=[(s,n,f,pp) for s,n,f,pp in g.dt2]
        for t in g.tables:
            if not t.face_offset: continue
            prim,cnt=struct.unpack_from('<HH',y,t.entry+0x3C)
            idx=struct.unpack_from('<%dH'%t.face_count,y,t.face_offset)
            lo,hi=struct.unpack_from('<HH',y,t.entry+0x40)
            vcount,vbase=struct.unpack_from('<HH',y,t.entry+0x38)
            ok=min(idx)>=lo and max(idx)<=hi
            c[(p.split('/')[-1],prim,'in range' if ok else 'OUT OF RANGE')]+=1
            if not ok and len(ex)<8: ex.append((p.split('/')[-1],x.name,prim,'idx',min(idx),max(idx),'range',lo,hi,'vc',vcount,vbase))
for k,v in sorted(c.items()): print(v,k)
for e in ex: print(e)
