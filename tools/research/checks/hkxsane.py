import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,os,collections,pickle,struct
from ds2 import streamfile, hkx
m=pickle.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'..','ds2','hkx_model.pkl'),'rb'))
SRC=sys.argv[1]; c=collections.Counter(); errs=collections.Counter()
for d,_,fs in os.walk(SRC):
  for f in fs:
    if not f.endswith('.str'): continue
    for a in streamfile.read(open(os.path.join(d,f),'rb').read())[1]:
        if a.type!='HKX': continue
        x=a.payload()
        if b'hkpStorageExtendedMeshShape' not in x: continue
        try: y=hkx.convert(m,x)
        except Exception as e: errs[repr(e)]+=1; continue
        objs,ptrs=hkx._fixups(x)
        for o,n in objs.items():
            if n=='hkpStorageExtendedMeshShapeMeshSubpartStorage':
                arr=[struct.unpack_from('<III',y,o+off) for off in (8,20,32,44,56,68,80)]
                for (pp,sz,cap) in arr:
                    if sz and (cap&0x3fffffff)<sz: c['badcap']+=1
                    if sz>10**7: c['hugesize']+=1
                nv=arr[0][1]; d0=ptrs.get(o+8)
                vs=[struct.unpack_from('<4f',y,d0+16*i) for i in range(nv)] if d0 else []
                if any(abs(v)>1e6 for q in vs for v in q[:3]): c['badvert']+=1
                d3=ptrs.get(o+44)
                if d3:
                    ix=struct.unpack_from('<%dI'%arr[3][1],y,d3)
                    if max(ix)>=nv: c['badidx32']+=1
                d2=ptrs.get(o+32)
                if d2:
                    ix=struct.unpack_from('<%dH'%arr[2][1],y,d2)
                    if max(ix)>=nv: c['badidx16']+=1
                c['mesh']+=1; c['idx16' if d2 else 'idx32' if d3 else 'idx8']+=1
            if n=='hkpStorageExtendedMeshShape':
                c['shape']+=1
                ref=struct.unpack_from('<HH',y,o+4); c['ref%s'%(ref,)]+=1
                nt=struct.unpack_from('<I',y,o+184)[0]; ns=struct.unpack_from('<I',y,o+196)[0]
                if nt>1000 or ns>1000: c['badsub']+=1
                t=ptrs.get(o+180)
                for i in range(nt if t else 0):
                    b=t+96*i
                    ntri,_,vstr,nverts=struct.unpack_from('<iIii',y,b+20)
                    if not(0<ntri<10**6 and vstr in (12,16) and 0<nverts<10**6): c['badtri']+=1
print(c, errs)
