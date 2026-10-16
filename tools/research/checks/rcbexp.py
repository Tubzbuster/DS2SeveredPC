import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,collections
import pairs
from ds2 import reloc
typ=sys.argv[1]; default={'BNK':'raw','RCB':'swap'}[typ]
P=[q for q in pairs.load(typ) if len(q[1])==len(q[2])]
def score(m,T):
    ex=bad=tot=0
    for k,x,p in T:
        y=m.convert(x)
        if y==p: ex+=1
        n=len(x)//4; tot+=n
        if y is None: bad+=n; continue
        bad+=sum(1 for i in range(n) if y[4*i:4*i+4]!=p[4*i:4*i+4])
    return '%d/%d exact, %.3f%% words'%(ex,len(T),100-100.0*bad/tot)
for opts in [dict(text_min=8),dict(text_min=8,bitsets=True),dict(text_min=8,bitsets=True,hash_kind=True)]:
    r=[]
    for tr,te in ((P[::2],P[1::2]),(P,P)):
        m=reloc.Model(default,**opts)
        for k,x,p in tr: m.train(x,p)
        m.finish(); r.append(score(m,te))
    print(typ,opts,'held-out',r[0],'| all',r[1])
