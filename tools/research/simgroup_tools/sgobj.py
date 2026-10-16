import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,os,struct; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from ds2 import streamfile, simgroup
from sgdump import dump
sch=simgroup.schema(); byname={v['name']:v for v in sch.values()}
def guid(b):
    w=struct.unpack('>4I',b); return '{%08X-%04X-%04X-%04X-%04X%08X}'%(w[0],w[1]>>16,w[1]&0xffff,w[2]>>16,w[2]&0xffff,w[3])
def fields(cn,rec,show=print):
    c=byname.get(cn)
    if not c: return
    for f in c['fields']:
        off,t,name=f[0],f[1],f[2]
        if off+4>len(rec): continue
        if t==17:
            h,z,rel=struct.unpack_from('>III',rec,off); s=rec[off+8+rel:rec.find(b'\0',off+8+rel)] if h else b''
            v='msg %08X %s'%(h,s.decode(errors='replace'))
        elif t==12: v='guid '+guid(rec[off:off+16])
        elif t==0: v='%g'%struct.unpack_from('>f',rec,off)[0]
        elif t in (1,2,10): v='%d / %08X'%(struct.unpack_from('>i',rec,off)[0],struct.unpack_from('>I',rec,off)[0])
        elif t in (5,7): v=str(rec[off])
        else: v='t%d %s'%(t,rec[off:off+8].hex())
        if v not in ('msg 00000000 ','guid {00000000-0000-0000-0000-000000000000}','0','0 / 00000000'): show('    %-40s %s'%(name,v))
def main():
    want=set(sys.argv[2:])
    for d,_,fs in os.walk(sys.argv[1]):
        for f in fs:
            if not f.endswith('.str'): continue
            for a in streamfile.read(open(os.path.join(d,f),'rb').read())[1]:
                if a.type!='SimGroup': continue
                for i,oh,cn,ln,strs,rec in dump(a.payload()):
                    if '%08X'%oh in want or any(w in ' '.join(strs) for w in want):
                        print(f, a.name, '%08X'%oh, cn); fields(cn,rec)
if __name__=='__main__': main()
