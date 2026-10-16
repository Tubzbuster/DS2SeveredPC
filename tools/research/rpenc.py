import random
def enc(data):
    out=bytearray([0x10,0xFB])+len(data).to_bytes(3,'big')
    i=0; n=len(data); lit=bytearray()
    def flush_lit(force=False):
        nonlocal lit
        while len(lit)>=4 and (len(lit)>3 or force):
            k=min(112,len(lit)//4*4)
            if k<4: break
            out.append(0xE0+((k-4)>>2)); out.extend(lit[:k]); del lit[:k]
    while i<n:
        best=(0,0)
        for off in range(1,min(i,2000)+1):
            l=0
            while i+l<n and l<1028 and data[i+l-off]==data[i+l]: l+=1
            if l>best[0]: best=(l,off)
        l,off=best
        if l>=5 and off<=131072:
            flush_lit()
            p=len(lit); assert p<=3
            # 4-byte form
            L=l-5; o=off-1
            out.extend([0xC0|((o>>12)&0x10)|((L>>6)&0x0C)|p, (o>>8)&0xFF, o&0xFF, L&0xFF]); out.extend(lit); lit=bytearray()
            i+=l
        else:
            lit.append(data[i]); i+=1
            if len(lit)>=112: flush_lit()
    flush_lit(True)
    out.append(0xFC|len(lit)); out.extend(lit)
    return bytes(out)
