import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,collections
from ds2 import streamfile, geo, build, volslots
c=collections.Counter(); keys=collections.Counter()
tab=build._model('volatile_table.pkl')
for p in sys.argv[1:]:
    mesh=None
    for a in streamfile.read(open(p,'rb').read())[1]:
        if a.type=='Mesh': mesh=geo.parse(a.payload(),True)
        elif a.type=='MeshVolatile':
            x=a.payload()
            for off,count,stride,flags in volslots.streams_in_volatile(mesh,len(x)):
                k=(volslots.fmt_key(flags),stride); keys[(k, k in tab)]+=1
            y=volslots.convert(tab,mesh,x)
            c['ok' if y is not None else 'NOT CONVERTED']+=1
print(c); 
for k,v in keys.most_common(): print(v,k)
