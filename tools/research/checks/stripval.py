import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,struct,collections
import pairs
from ds2 import geo, build, meshconv
tm=build._model('mesh_templates.pkl')
def tris(d,t):
    prim,n=struct.unpack_from('<HH',d,t.entry+0x3C)
    idx=struct.unpack_from('<%dH'%t.face_count,d,t.face_offset)
    out=collections.Counter()
    if prim==5:
        for i in range(len(idx)-2):
            a,b,c=idx[i:i+3]
            if len({a,b,c})<3: continue
            if i%2: a,b=b,a
            m=min(range(3),key=lambda k:(a,b,c)[k]); tr=(a,b,c)[m:]+(a,b,c)[:m]
            out[tr]+=1
    else:
        for i in range(0,len(idx)-2,3):
            a,b,c=idx[i:i+3]; m=min(range(3),key=lambda k:(a,b,c)[k]); out[(a,b,c)[m:]+(a,b,c)[:m]]+=1
    return prim,set(out),max(idx) if idx else 0
P=pairs.load('Mesh'); c=collections.Counter(); ex=[]
for k,x,p in P:
    if x[:4]!=b'EAGM': continue
    try: g=geo.parse(x,True); gp=geo.parse(p,False)
    except Exception: continue
    if len(g.tables)!=len(gp.tables): continue
    if not any(struct.unpack_from('>H',x,t.entry+0x3C)[0]==6 for t in g.tables): continue
    y=meshconv.convert(x,tm); gy=geo.parse(y,False)
    c['meshes']+=1
    if len(y)==len(p): c['samelen']+=1
    for t,ty,tp in zip(g.tables,gy.tables,gp.tables):
        if not t.face_offset: continue
        a=tris(y,ty); b=tris(p,tp)
        c['prim ok' if a[0]==b[0] else 'prim bad']+=1
        c['tris same' if a[1]==b[1] else 'tris diff']+=1
        if a[1]!=b[1] and len(ex)<5: ex.append((k[1],len(a[1]),len(b[1]),len(a[1]^b[1])))
    # volatile pointers consistent
    for (s1,n1,f1,p1),(s2,n2,f2,p2) in zip(gy.dt2,gp.dt2):
        if p2>=gp.local_uv_offset: c['volrel ok' if p1-gy.local_uv_offset==p2-gp.local_uv_offset else 'volrel bad']+=1
print(c.most_common()); print(ex)
c2=collections.Counter()
for k,x,p in P:
    if x[:4]!=b'EAGM': continue
    try: g=geo.parse(x,True); gp=geo.parse(p,False)
    except Exception: continue
    if len(g.tables)!=len(gp.tables) or not any(struct.unpack_from('>H',x,t.entry+0x3C)[0]==6 for t in g.tables): continue
    y=meshconv.convert(x,tm); gy=geo.parse(y,False)
    for ty,tp in zip(gy.tables,gp.tables):
        a=struct.unpack_from('<I',y,ty.entry+0x8C)[0]; b=struct.unpack_from('<I',p,tp.entry+0x8C)[0]
        if not a: continue
        c2['same' if y[a:a+64]==p[b:b+64] else 'diff']+=1
    # names / header 0x4C region
    for o in (0x20,0x4C):
        a=struct.unpack_from('<I',y,o)[0]; b=struct.unpack_from('<I',p,o)[0]
        c2['h%x '%o+('same' if y[a:a+32]==p[b:b+32] else 'diff')]+=1
    if len(y)>gy.local_uv_offset: c2['tail beyond L']+=1
print(c2)
