from dsx import *
import re,struct
def u32(v): return struct.unpack_from('<I',d,v2f(v))[0]
REG={}
# scan .text for hkClass registrations: ... push nmembers; push members; ...; push size; push parent; push name; mov ecx, cls; call
for m in re.finditer(rb'\x68(....)\xb9(....)\xe8',TX,re.S):
    name=struct.unpack('<I',m.group(1))[0]; cls=struct.unpack('<I',m.group(2))[0]
    s=cstr(name) if v2f(name) else None
    if not s or not s.startswith('hk'): continue
    st=m.start()
    # walk back pushes
    pushes=[]; q=st
    for ins in reversed(list(md.disasm(TX[st-60:st+5],TX0+st-60))):
        pass
    seg=list(md.disasm(TX[st-40:st],TX0+st-40))
    vals=[]
    for ins in seg:
        if ins.mnemonic=='push':
            try: vals.append(int(ins.op_str,16))
            except: vals.append(None)
    REG[s]=(cls,vals)
def members(name):
    cls,vals=REG[name]
    # vals: [..., nmem?, members, 0,0,0,0, size, parent] (last pushes before name)
    return vals
if __name__=='__main__':
    import sys
    for n in sys.argv[1:]: print(n, [hex(v) if v is not None else None for v in REG.get(n,(0,[]))[1]])
