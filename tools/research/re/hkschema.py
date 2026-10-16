from mem import *
import json
BYCLS={v[0]:k for k,v in REG.items()}
def info(name):
    cls,vals=REG[name]
    # vals end: ..., nmem, members, a,b,c,d, size, parent
    nm,mp,size,parent=vals[-8],vals[-7],vals[-2],vals[-1]
    return dict(size=size, parent=BYCLS.get(parent) if parent else None, nmem=nm, mp=mp)
def schema(roots):
    out={}; todo=list(roots)
    while todo:
        n=todo.pop()
        if n in out or n is None: continue
        i=info(n); ms=[]
        for (mn,ty,st,ca,fl,off,cl,en) in (mems(i['mp'],i['nmem']) if i['nmem'] else []):
            c=BYCLS.get(int(cl,16)) if cl else None
            ms.append([mn,ty,st,ca,off,c])
            if c and ty in (25,22,26,23) : todo.append(c)
        out[n]=dict(size=i['size'],parent=i['parent'],members=ms)
        todo.append(i['parent'])
    return out
if __name__=='__main__':
    import sys
    s=schema(sys.argv[1:])
    for k,v in s.items(): print(k,v)
