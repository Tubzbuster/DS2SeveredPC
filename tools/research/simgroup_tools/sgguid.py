import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,os,struct; sys.path.insert(0,os.path.dirname(__file__))
from ds2 import streamfile, simgroup
from sgdump import dump
from sgobj import guid
def objects(x):
    hsz,o8,oC,o10=struct.unpack_from('>IIII',x,4); n14,n16,n18=struct.unpack_from('>HHH',x,0x14)
    recs={oh:(cn,strs) for i,oh,cn,ln,strs,rec in dump(x)}
    for i in range(n14):
        e=oC+0x44*i
        hoff=struct.unpack_from('>I',x,e+8)[0]; g=guid(x[e+12:e+28])
        oh=struct.unpack_from('>I',x,hoff)[0] if hoff+4<=len(x) else None
        yield g,oh,recs.get(oh)
if __name__=='__main__':
    want=set(a.upper() for a in sys.argv[2:])
    for d,_,fs in os.walk(sys.argv[1]):
      for f in fs:
        if not f.endswith('.str'): continue
        for a in streamfile.read(open(os.path.join(d,f),'rb').read())[1]:
            if a.type!='SimGroup': continue
            try:
                for g,oh,r in objects(a.payload()):
                    if g in want: print(f,g,'%08X'%oh if oh else oh,r[0] if r else None,(r[1][-3:] if r else ''))
            except Exception as e: pass
