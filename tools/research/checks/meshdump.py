import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,os,struct
from ds2 import streamfile, geo
f=sys.argv[1]; want=int(sys.argv[2]) if len(sys.argv)>2 else 0
n=0
for a in streamfile.read(open(f,'rb').read())[1]:
    if a.type!='Mesh': continue
    x=a.payload(); g=geo.parse(x,True)
    if not any(t.lod_type==6 for t in g.tables): continue
    if n<want: n+=1; continue
    print(a.name, hex(len(x)), 'tables',g.table_count,'luv',hex(g.local_uv_offset))
    for o in range(0,0x100,16): print(' %03x'%o,' '.join('%08x'%v for v in struct.unpack_from('>4I',x,o)))
    for t in g.tables[:2]:
        print(' DT1 @%x'%t.entry)
        for o in range(0,0xC0,16): print('  %02x'%o,' '.join('%08x'%v for v in struct.unpack_from('>4I',x,t.entry+o)))
        print('  table_offset',hex(t.table_offset),'face',hex(t.face_offset),t.face_count,'vert',hex(t.vert_offset),t.vert_count)
        for o in range(t.table_offset,t.table_offset+0x40,16): print('  T%03x'%o,' '.join('%08x'%v for v in struct.unpack_from('>4I',x,o)))
    print(' DT2',[(hex(a),b,c.hex(),hex(d)) for a,b,c,d in g.dt2])
    break
