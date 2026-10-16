import os as _os, sys as _sys; _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
import sys,struct,collections
import pairs
M=0xffffffff
def sdbm(b,h=0):
    for c in b: h=(h*65599+c)&M
    return h
def conv_header(x):
    hsz=struct.unpack_from('>I',x,4)[0]; B=(hsz+15)//16*16
    n=B//4
    out=bytearray(struct.pack('<%dI'%n,*struct.unpack_from('>%dI'%n,x,0)))
    for o in (0x14,0x18):
        w=x[o:o+4]; out[o:o+4]=bytes((w[1],w[0],w[3],w[2]))
    o10=struct.unpack_from('>I',x,0x10)[0]; n18=struct.unpack_from('>H',x,0x18)[0]
    if o10:
        for i in range(n18):
            e=struct.unpack_from('>I',x,o10+4*i)[0]
            h,cnt=struct.unpack_from('>II',x,e)
            hs=[struct.unpack_from('>I',x,q)[0] for q in struct.unpack_from('>%dI'%cnt,x,e+8)]
            out[e:e+4]=struct.pack('<I',sdbm(struct.pack('<%dI'%cnt,*hs)))
    return bytes(out),B
P=[q for q in pairs.load('SimGroup') if len(q[1])==len(q[2])]
c=collections.Counter(); bad=collections.Counter()
for k,x,p in P:
    y,B=conv_header(x)
    if y==p[:B]: c['ok']+=1
    else:
        c['bad']+=1
        for o in range(0,B,4):
            if y[o:o+4]!=p[o:o+4]: bad[o if o<0x3c else 'later']+=1
print(c, bad.most_common(10))
reg=collections.Counter()
for k,x,p in P:
    y,B=conv_header(x)
    h=struct.unpack_from('>5I4H',x,0)
    o8,oC,o10=h[2],h[3],h[4]; n14,n16=h[5],h[6]
    for o in range(0,B,4):
        if y[o:o+4]!=p[o:o+4]:
            if o8<=o<o8+4*n14: r='hashlist'
            elif oC<=o<oC+0x44*n16: r='obj+%x'%((o-oC)%0x44)
            elif o10 and o>=o10: r='groups'
            else: r='other'
            reg[r]+=1
print(reg.most_common(20))
