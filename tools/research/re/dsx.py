import struct, sys, re
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
import os
# the user's unwrapped retail exe (static analysis only; never commit it)
EXE=os.environ.get('DS2_EXE','deadspace2.exe')
d=open(EXE,'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]; n=struct.unpack_from('<H',d,pe+6)[0]; opt=struct.unpack_from('<H',d,pe+20)[0]
BASE=struct.unpack_from('<I',d,pe+24+28)[0]
SECS=[]
for i in range(n):
    o=pe+24+opt+40*i; vs,va,rs,ra=struct.unpack_from('<IIII',d,o+8); SECS.append((d[o:o+8].rstrip(b'\0'),va,vs,ra,rs))
def v2f(v):
    for nm,va,vs,ra,rs in SECS:
        if BASE+va<=v<BASE+va+rs: return v-BASE-va+ra
def f2v(off):
    for nm,va,vs,ra,rs in SECS:
        if ra<=off<ra+rs: return BASE+va+off-ra
TXT=SECS[0]; TX0=BASE+TXT[1]; TX=d[TXT[3]:TXT[3]+TXT[4]]
md=Cs(CS_ARCH_X86, CS_MODE_32)
def cstr(v):
    f=v2f(v)
    if f is None: return None
    e=d.find(b'\0',f)
    s=d[f:e]
    if 2<=len(s)<200 and all(32<=c<127 for c in s): return s.decode()
    return None
def dis(start, count=80):
    out=[]
    for ins in md.disasm(d[v2f(start):v2f(start)+count*8], start):
        ann=''
        for m in re.findall(r'0x[0-9a-f]{6,8}', ins.op_str):
            s=cstr(int(m,16))
            if s: ann+=' ; "%s"'%s
        out.append('%08x  %-6s %s%s'%(ins.address, ins.mnemonic, ins.op_str, ann))
        if len(out)>=count: break
    return out
def func_start(v):
    # scan back for typical prologue / int3 padding
    f=v2f(v)
    for i in range(f, f-0x4000, -1):
        if d[i-1] in (0xcc,0xc3,0x90) and d[i:i+3] in (b'\x55\x8b\xec',) : return f2v(i)
        if d[i-1]==0xcc and d[i] in (0x83,0x81,0x6a,0x51,0x53,0x56,0x57,0x8b,0x55,0xa1,0x64): return f2v(i)
    return None
def xrefs_to(target, kinds=(b'\xe8',)):
    res=[]
    for i in range(len(TX)-5):
        if TX[i]==0xe8:
            rel=struct.unpack_from('<i',TX,i+1)[0]
            if TX0+i+5+rel==target: res.append(TX0+i)
    return res
def imm_refs(v):
    k=struct.pack('<I',v); return [TX0+m.start() for m in re.finditer(re.escape(k),TX)]
if __name__=='__main__':
    a=int(sys.argv[1],16); c=int(sys.argv[2]) if len(sys.argv)>2 else 60
    print('\n'.join(dis(a,c)))

def thunks_to(target):
    res=[]
    for i in range(min(len(TX)-5, 0x10000)):
        if TX[i]==0xe9 and TX0+i+5+struct.unpack_from('<i',TX,i+1)[0]==target: res.append(TX0+i)
    return res
def all_callers(target):
    out=[]
    for t in [target]+thunks_to(target):
        out+= [(t,c) for c in xrefs_to(t)] + [(t,('ptr',x)) for x in imm_refs(t)]
    return out
