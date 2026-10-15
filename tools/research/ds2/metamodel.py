"""MetaModel ('MMdl' v14): a small object graph.

Header: ids at 0x10-0x2F, 8 table pointers at 0x34 and 8 u16 counts at 0x58.
Tables with fixed records: 0 (32 bytes), 1 (48), 2 (12), 3 (24), 4 (12),
5 (36), 6 (36, same layout as 5). Tables are followed by u32 pointer lists;
the last one before table 7 by the string table (raw text). Table 7 points
at the trailing data (floats). Most fields are 32-bit; a few record
fields are pairs of u16 (count, kind), learned as templates per table.
"""
import struct

REC = {0: 32, 1: 48, 2: 12, 3: 24, 4: 12, 5: 36, 6: 36}


def regions(x, be=True):
    """Yields (start, end, kind) covering the payload; kind is 'hdr',
    ('rec', table) , 'str' or 'u32'."""
    e = '>' if be else '<'
    ptrs = struct.unpack_from(e + '8I', x, 0x34)
    cnt = struct.unpack_from(e + '8H', x, 0x58)
    out = [(0, 0x68, 'hdr')]
    marks = sorted(set([q for q in ptrs if q] + [len(x)]))
    # strings start at the lowest name referenced by tables 1, 5 and 6
    names = [struct.unpack_from(e + 'I', x, ptrs[s] + REC[s] * i + f)[0]
             for s in (1, 5, 6) if ptrs[s] for i in range(cnt[s]) for f in (4, 8)]
    first_str = min([q for q in names if q > 0x68] + [len(x)])
    for t in range(8):
        if not ptrs[t]:
            continue
        nxt = min(q for q in marks if q > ptrs[t])
        if t in REC:
            end = ptrs[t] + REC[t] * cnt[t]
            out.append((ptrs[t], end, ('rec', t)))
            # then u32 pointer lists, and maybe the strings
            if end <= first_str < nxt:
                out.append((end, first_str, 'u32'))
                out.append((first_str, nxt, 'str'))
            elif end < nxt:
                out.append((end, nxt, 'u32'))
        else:
            out.append((ptrs[t], nxt, 'u32'))
    out.sort()
    return out, ptrs, cnt


# Fixed record layouts: word index -> byte order ('s' 32-bit swap, 'p' u16
# pair, 'r' raw). Learned from the PC/360 pairs (see tools/research).
LAYOUT = {
    'hdr': 's' * 22 + 'pppp',
    0: 'sssssssr',
    1: 'sssssssspssp',
    2: 'ssp',
    3: 'ssssss',
    4: 'ssp',
    5: 'ssssssssp',
    6: 'ssssssssp',
}
BOOL = 1   # table 3 value type whose value is a byte, stored as is


def _words(out, x, a, layout):
    for i, c in enumerate(layout):
        o = a + 4 * i
        w = x[o:o + 4]
        if c == 's':
            out[o:o + 4] = w[::-1]
        elif c == 'p':
            out[o:o + 4] = bytes((w[1], w[0], w[3], w[2]))
        else:
            out[o:o + 4] = w


def convert(x):
    if x[:4] != b'MMdl' or struct.unpack_from('>I', x, 4)[0] != 14:
        return None
    rg, ptrs, cnt = regions(x)
    out = bytearray(len(x))
    n = len(x) // 4 * 4
    out[:n] = struct.pack('<%dI' % (n // 4), *struct.unpack('>%dI' % (n // 4), x[:n]))
    out[n:] = x[n:]
    for a, b, kind in rg:
        if kind == 'str':
            out[a:b] = x[a:b]
        elif kind == 'hdr':
            _words(out, x, a, LAYOUT['hdr'])
        elif kind != 'u32':
            t = kind[1]
            for o in range(a, b, REC[t]):
                _words(out, x, o, LAYOUT[t])
                if t == 3 and struct.unpack_from('>I', x, o + 20)[0] == BOOL:
                    out[o:o + 4] = x[o:o + 4]
                if t == 4:
                    # a value for the table 2 entry it points at, whose kind
                    # (u16 at +8) 1 is a bool: stays as is
                    r = struct.unpack_from('>I', x, o + 4)[0]
                    if ptrs[2] <= r < ptrs[2] + 12 * cnt[2] and struct.unpack_from('>H', x, r + 8)[0] == 1:
                        out[o:o + 4] = x[o:o + 4]
    out[0:4] = x[0:4][::-1]
    return bytes(out)
