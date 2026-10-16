import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,struct,collections
import pairs
from ds2 import geo, build, meshconv
tm=build._model('mesh_templates.pkl'); c=collections.Counter()
for k,x,p in pairs.load('Mesh'):
    if x[:4]!=b'EAGM': continue
    try: g=geo.parse(x,True); gp=geo.parse(p,False)
    except Exception: continue
    if len(g.tables)!=len(gp.tables) or not any(struct.unpack_from('>H',x,t.entry+0x3C)[0]==6 for t in g.tables): continue
    y=meshconv.convert(x,tm); gy=geo.parse(y,False)
    for ty,tp in zip(gy.tables,gp.tables):
        a=struct.unpack_from('<I',y,ty.entry+0x8C)[0]; b=struct.unpack_from('<I',p,tp.entry+0x8C)[0]
        if not a: continue
        c['floats '+('same' if y[a:a+0x30]==p[b:b+0x30] else 'diff')]+=1
        hy=struct.unpack_from('<5H',y,a+0x30); hp=struct.unpack_from('<5H',p,b+0x30)
        c['hdr '+('same' if hy==hp else 'diff')]+=1
        if hy==hp:
            n=hy[3]; m=hy[4]+1
            c['offs '+('same' if y[a+0x3A+2*n:a+0x3A+2*n+2*m]==p[b+0x3A+2*n:b+0x3A+2*n+2*m] else 'diff')]+=1
            ry=struct.unpack_from('<%dH'%n,y,a+0x3A); rp=struct.unpack_from('<%dH'%n,p,b+0x3A)
            c['refs exact']+=sum(u==v for u,v in zip(ry,rp)); c['refs within 3']+=sum(abs(u-v)<=3 for u,v in zip(ry,rp)); c['refs']+=n
print(c)
