"""360 -> PC payload converters, one per asset type, worked out from the
exported PC/360 pairs and scored by tools/research/score.py (exact byte
match against the real PC asset)."""
import struct


def be32(b, o): return struct.unpack_from('>I', b, o)[0]
def be16(b, o): return struct.unpack_from('>H', b, o)[0]
def le32(v): return struct.pack('<I', v & 0xFFFFFFFF)
def le16(v): return struct.pack('<H', v & 0xFFFF)


def swap32(b):
    n = len(b) // 4 * 4
    out = bytearray(b)
    out[:n] = struct.pack('<%dI' % (n // 4), *struct.unpack('>%dI' % (n // 4), b[:n]))
    return bytes(out)


def swap16(b):
    n = len(b) // 2 * 2
    out = bytearray(b)
    out[:n] = struct.pack('<%dH' % (n // 2), *struct.unpack('>%dH' % (n // 2), b[:n]))
    return bytes(out)


def lua(x):
    return x


def tob(x):
    return swap32(x)


def tg4d(x):
    return swap16(x)


X360_ONLY_TEX_ATTR = 0x927E6ABF   # attribute present only in 360 texture headers
TEX_SIZE_ATTR = 0x4F8B2A9F        # attribute holding the texture data size


def tg4h(x):
    """Texture header.

    Layout: fixed fields (0x00-0x2F), an attribute table at [0x28] of N
    (byte 0x27) u32 hashes, then at [0x2C] N entries of (u8 kind, u32 value)
    (kind 0: offset of a string in the tail, kind 1: integer), then strings.
    360 -> PC: drop the 360-only attribute, set the size attribute to the
    real data size (field 0x1C; the 360 one is padded), little-endian
    fields, and move offsets back by the bytes removed.
    """
    n = x[0x27]
    tab, ent = be32(x, 0x28), be32(x, 0x2C)
    if x[4] != 4 or tab != 0x30 or ent != tab + 4 * n or len(x) < ent + 5 * n:
        return None
    attrs = []
    for i in range(n):
        h = be32(x, tab + 4 * i)
        kind = x[ent + 5 * i]
        val = be32(x, ent + 5 * i + 1)
        attrs.append((h, kind, val))
    kept = [a for a in attrs if a[0] != X360_ONLY_TEX_ATTR]
    d = 9 * (len(attrs) - len(kept))
    o = bytearray()
    o += le32(be32(x, 0) - d)
    o += bytes([x[4], 0]) + le16(be16(x, 6))
    for off in (8, 0xC, 0x10, 0x14):
        o += le32(be32(x, off))
    o += le32(be32(x, 0x18) - d)
    o += le32(be32(x, 0x1C))
    o += le16(be16(x, 0x20)) + le16(be16(x, 0x22))
    o += x[0x24:0x27] + bytes([len(kept)])
    o += le32(tab) + le32(tab + 4 * len(kept))
    for h, kind, val in kept:
        o += le32(h)
    for h, kind, val in kept:
        if kind == 0:
            val -= d
        elif h == TEX_SIZE_ATTR:
            val = be32(x, 0x1C)
        o += bytes([kind]) + le32(val)
    o += x[ent + 5 * n:]
    return bytes(o)


_MAT_TABLE = None


def _material_table():
    global _MAT_TABLE
    if _MAT_TABLE is None:
        import json, os
        _MAT_TABLE = json.load(open(os.path.join(os.path.dirname(__file__), 'material_table.json')))
    return _MAT_TABLE


def material(x):
    """Material: byte-swap the structure, replace the 3 shader passes with
    their PC equivalents (learned table, keyed by the 360 passes), and append
    the parameter copies the PC shaders need (new value slots at the end of
    the hash list, holding the same values)."""
    from . import material as M
    m = M.parse(x, True)
    key = ','.join('%08X:%08X:%08X:%s' % (s, f, t, tl.hex()) for s, f, t, tl in m.passes)
    rule = _material_table().get(key)
    if rule is None:
        return None
    m.passes = []
    for item in rule['pc'].split(','):
        s, f, t, tl = item.split(':')
        m.passes.append((int(s, 16), int(f, 16), int(t, 16), bytes.fromhex(tl)))
    by_hash = {q[0]: q for q in m.params}
    nvals = len(m.hashes)
    for h in rule['append']:
        q = by_hash[int(h, 16)]
        m.params.append((q[0], q[1], q[2], 4 * nvals, q[4], q[5]))
        m.hashes.append(m.hashes[q[3] // 4])
        nvals += 1
    # bytes kept in stored order: flag byte groups at 0x10 and 0x20
    w0 = m.zero10[0:4]
    m.zero10 = w0 + struct.pack('<II', *struct.unpack('>II', m.zero10[4:12]))
    d_bytes = struct.pack('>I', m.d)
    m.d = struct.unpack('<I', d_bytes)[0]
    m.zero10 = m.zero10  # already in PC order
    pad = lambda n: b'\0' * ((16 - n % 16) % 16)
    m.gap1 = pad(0x70 + 12 * len(m.params))
    out = M.write(m, False)
    # write() packed zero10 verbatim; flag word 0 must stay in stored byte order
    return out


def metamodel(x):
    from . import metamodel as M
    return M.convert(x)


def simgroup(x):
    from . import simgroup as S
    return S.convert(x)


_RELOC = {}


def _reloc(typ, x):
    """relocation-table types: blocks with learned templates
    (ds2/<type>_model.pkl from learn_reloc.py / learn_bnk.py)"""
    if typ not in _RELOC:
        import os, pickle
        _RELOC[typ] = pickle.load(open(os.path.join(os.path.dirname(__file__), typ.lower() + '_model.pkl'), 'rb'))
    return _RELOC[typ].convert(x)


def bnk(x):
    """BNK: learned templates, then the blend weight of 08 01 nodes: the
    node's first child starts with a float (2.0 in the base game; swapped
    in all 198 pairs). Its block is typed by that float's first byte, so
    its template is a near-random one (0x4332924A in
    pdlc1_gps_02_01_player.bnk stayed raw and the hold pose never ended)."""
    from . import reloc
    y = _reloc('BNK', x)
    info = reloc.parse(x) if y is not None else None
    if info:
        y = bytearray(y)
        for f, v in info['ptrs'].items():
            if f >= 4 and x[f - 4] == 0x08 and x[f - 3] == 0x01 and v + 4 <= info['R']:
                y[v:v + 4] = x[v:v + 4][::-1]
        y = bytes(_bnk_param_types(x, y))
    return y


def _bnk_param_types(x, y):
    """{u32 type, u32 value} parameter records (type 1 a float such as
    +-1.0, type 2 an id): the templates sometimes leave the type word raw
    while swapping its value. A type 1 or 2 left raw right before a value
    that was swapped is swapped too (54 such words in the 147 PC/360 pairs,
    all fixed, none broken)."""
    y = bytearray(y)
    for i in range(0, len(x) - 7, 4):
        a, nxt = x[i:i + 4], x[i + 4:i + 8]
        if a in (b'\0\0\0\x01', b'\0\0\0\x02') and y[i:i + 4] == a and nxt != nxt[::-1] \
                and y[i + 4:i + 8] == nxt[::-1]:
            y[i:i + 4] = a[::-1]
    return y


def rcb(x):
    return _reloc('RCB', x)


def nav(x):
    from . import nav as N
    return N.convert(x)


_HKX = None


def hkx(x):
    """Havok packfile: blocks typed by class / member, learned templates
    (ds2/hkx_model.pkl from learn_hkx.py)."""
    global _HKX
    from . import hkx as H
    if _HKX is None:
        import os, pickle
        _HKX = pickle.load(open(os.path.join(os.path.dirname(__file__), 'hkx_model.pkl'), 'rb'))
    return H.convert(_HKX, x)


def smb(x):
    from . import smb as S
    return S.convert(x)


def lh2(x):
    from . import lh2 as L
    return L.convert(x)


_POS = {}


def _postmpl(typ, x):
    """small fixed-layout types: per-position template (learn_postmpl.py);
    positions past it are swapped"""
    from . import templates as T
    if typ not in _POS:
        import os, pickle
        _POS[typ] = pickle.load(open(os.path.join(os.path.dirname(__file__), typ.lower() + '_postmpl.pkl'), 'rb'))
    pm = _POS[typ]
    m = len(x) // 4
    q = pm[:m] + [T.PERMS[T.SWAP]] * (m - len(pm))
    return T.apply(q, x[:4 * m], union_swap=True) + x[4 * m:]


def anim(x):
    """ANIM (camera and scripted animations): a header (magic, two floats,
    track count at 0x0C, track list offset at 0x10), the tracks (two hashes
    and a header offset each), the track headers (count, type as two u16,
    data offset) and float keys. All 32-bit words except the type, two u16.
    Exact on all 51 PC/360 pairs; the position template it replaces (37/51)
    swapped the type as one word in files laid out unlike the pairs (the
    landing bay camera se_02_16_cam read its tracks as type 0)."""
    if len(x) < 0x14 or len(x) % 4:
        return _postmpl('ANIM', x)
    n, lst = struct.unpack_from('>II', x, 0x0C)
    if lst + 12 * n > len(x):
        return _postmpl('ANIM', x)
    out = bytearray(len(x))
    for o in range(0, len(x), 4):
        out[o:o + 4] = x[o:o + 4][::-1]
    for i in range(n):
        h = struct.unpack_from('>I', x, lst + 12 * i + 8)[0]
        if h + 12 > len(x):
            return _postmpl('ANIM', x)
        out[h + 4:h + 8] = x[h + 4:h + 6][::-1] + x[h + 6:h + 8][::-1]
    return bytes(out)


def png(x):
    return x                      # standard PNG files, same on every platform


_REGION = {}


def _region(typ, x):
    from . import regionmodel
    import os
    if typ not in _REGION:
        _REGION[typ] = regionmodel.Model.load(os.path.join(os.path.dirname(__file__), typ.lower() + '_model.json'))
    return _REGION[typ].convert(x)


def graph(x):
    return _region('Graph', x)


def ism(x):
    return _region('ISM', x)


def light_toc(x):
    from . import lighttoc as L
    return L.light_toc(x)


def variable_dictionary(x):
    from . import lighttoc as L
    return L.variable_dictionary(x)


def sbk(x):
    from . import sbk as S
    return S.convert(x)


def snu(x):
    from . import snu as S
    return S.convert(x)


CONVERTERS = {'LUA': lua, 'TOB': tob, 'tg4d': tg4d, 'tg4h': tg4h, 'Material': material,
              'MetaModel': metamodel, 'SimGroup': simgroup, 'BNK': bnk, 'NAV': nav, 'HKX': hkx, 'RCB': rcb, 'SMB': smb, 'LH2': lh2, 'ANIM': anim, 'PNG': png, 'SNU': snu, 'SBK': sbk, 'Graph': graph, 'ISM': ism,
              'LightTOC': light_toc, 'VariableDictionary': variable_dictionary}
