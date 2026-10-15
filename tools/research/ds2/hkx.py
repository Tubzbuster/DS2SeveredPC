"""Havok 6.5 packfiles (.hkx). Header (0x40), section headers (0x30 each:
name, absolute data start, then local / global / virtual fixups, exports,
imports, end, relative to the start). __classnames__: entries (u32
signature, 0x09, name). __data__: objects, typed by the virtual fixups
(object offset -> class name), and the arrays / blocks their pointers
reach (local fixups: pointer offset -> target; global fixups: pointer
offset -> section, target). Fixup tables are pairs / triples of u32.

Byte orders are learned per block type (ds2/blockmodel.py): objects by class
name, pointed-to blocks by (parent type, pointer offset).
"""
import bisect
import struct
from .blockmodel import Layout, Model

MAGIC = b'\x57\xe0\xe0\x57\x10\xc0\xc0\x10'


def _sections(x):
    n = struct.unpack_from('>I', x, 0x14)[0]
    out = []
    for i in range(n):
        o = 0x40 + 0x30 * i
        name = x[o:o + 19].split(b'\0')[0].decode('latin1')
        out.append((name, o, struct.unpack_from('>7I', x, o + 20)))
    return out


def layout(x):
    if x[:8] != MAGIC or len(x) < 0x40 or x[0x11] != 0:
        return None
    try:
        secs = _sections(x)
    except struct.error:
        return None
    swap = []
    raw = []
    blocks = [(0, 0x40, ('hdr',))]
    raw.append((0x28, 0x38))                              # version string
    for name, o, f in secs:
        raw.append((o, o + 20))
        blocks.append((o + 20, o + 0x30, ('sechdr',)))
    names = {}
    for idx, (name, o, f) in enumerate(secs):
        start, loc, glob, virt, exp, imp, end = f
        if name == '__classnames__':
            q = start
            while q + 5 <= start + loc:
                if x[q:q + 4] == b'\xff\xff\xff\xff':
                    break
                e = x.find(b'\0', q + 5, start + loc)
                if e < 0:
                    break
                names[(idx, q + 5 - start)] = x[q + 5:e].decode('latin1')
                # signature: unaligned u32 -> handled in convert_hkx
                q = e + 1
            raw.append((start, start + loc))
        if name != '__data__':
            continue
        def fix(a, b, k):
            out = []
            for q in range(start + a, start + b - 4 * k + 1, 4 * k):
                v = struct.unpack_from('>%dI' % k, x, q)
                if v[0] == 0xFFFFFFFF:
                    continue
                out.append(v)
            for q in range(start + a, start + b, 4):
                swap.append(q)
            return out
        local = fix(loc, glob, 2)
        glob_ = fix(glob, virt, 3)
        virtual = fix(virt, exp, 3)
        objs = {}
        for src, sec, off in virtual:
            objs[src] = names.get((sec, off), '?')
        targets = set(objs) | {dst for src, dst in local} | {dst for src, s, dst in glob_ if s == idx}
        starts = sorted(t for t in targets if t < loc)
        types = {s: ('obj', objs[s]) for s in objs}
        ptrs = sorted([(src, dst) for src, dst in local] + [(src, dst) for src, s, dst in glob_ if s == idx])
        for src, dst in ptrs:
            swap.append(start + src)
        # parents: breadth-first from the objects
        by_block = {}
        for src, dst in ptrs:
            i = bisect.bisect_right(starts, src) - 1
            if i >= 0:
                by_block.setdefault(starts[i], []).append((src, dst))
        order = list(sorted(objs))
        k = 0
        while k < len(order):
            b = order[k]; k += 1
            for src, dst in by_block.get(b, []):
                if dst not in types:
                    pt = types[b]
                    types[dst] = (pt[1] if pt[0] == 'obj' else pt, src - b)
                    order.append(dst)
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else loc
            blocks.append((start + s, start + e, types.get(s, ('orphan',))))
    return Layout(blocks, swap=swap, raw=raw, limit=None, text=False)


def keys(typ):
    if typ[0] == 'obj':
        return [typ, ('any',)]
    if len(typ) == 2 and isinstance(typ[1], int):
        return [typ, ('member', typ[1]), ('any',)]
    return [typ, ('any',)]


def new_model():
    return Model(layout, keys, q64=True)


def convert(model, x):
    lay = layout(x)
    if lay is None:
        return None
    out = bytearray(model.convert(x, lay))
    out[0x11] = 1                                     # layout rules: little endian
    # class name signatures (unaligned u32)
    for name, o, f in _sections(x):
        if name == '__classnames__':
            start, loc = f[0], f[1]
            q = start
            while q + 5 <= start + loc and x[q:q + 4] != b'\xff\xff\xff\xff':
                e = x.find(b'\0', q + 5, start + loc)
                if e < 0:
                    break
                out[q:q + 4] = x[q:q + 4][::-1]
                q = e + 1
    return bytes(out)
