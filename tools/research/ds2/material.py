"""Material asset (magic 0x0AA0DEED) parser/writer for both byte orders.

Layout (offsets as stored):
  0x00 u32 magic, u16 version, u16 0
  0x08 u32 a, u32 b, 12 zero bytes, u32 c, u32 d
  0x24 3 passes x 16 bytes: u32 shader, u32 flags, u32 technique, 4 bytes
  0x54 u16[8]: 0, nparams, params_off, params_size, hashes_off,
               hashes_size, strings_off, strings_size
  0x64 12 zero bytes
  params: n x (u32 hash, u8 kind, u8 x, u16 a, u16 b, u16 c)
  hashes: u32 each
  strings: NUL-separated
"""
import struct


class Material:
    pass


def parse(b, be):
    E = '>' if be else '<'
    m = Material()
    m.magic, m.ver, m.ver2 = struct.unpack_from(E + 'IHH', b, 0)
    m.a, m.b = struct.unpack_from(E + 'II', b, 8)
    m.zero10 = b[0x10:0x1C]
    m.c, m.d = struct.unpack_from(E + 'II', b, 0x1C)
    m.passes = []
    for i in range(3):
        o = 0x24 + 16 * i
        s, f, t = struct.unpack_from(E + 'III', b, o)
        m.passes.append((s, f, t, bytes(b[o + 12:o + 16])))
    m.table = struct.unpack_from(E + '8H', b, 0x54)
    m.zero64 = b[0x64:0x70]
    _, n, po, ps, ho, hs, so, ss = m.table
    m.params = []
    for i in range(n):
        o = po + 12 * i
        h, = struct.unpack_from(E + 'I', b, o)
        k, x = b[o + 4], b[o + 5]
        a1, a2, a3 = struct.unpack_from(E + 'HHH', b, o + 6)
        m.params.append((h, k, x, a1, a2, a3))
    m.gap1 = b[po + 12 * n:ho]
    m.hashes = list(struct.unpack_from(E + '%dI' % (hs // 4), b, ho))
    m.gap2 = b[ho + hs:so]
    m.strings = bytes(b[so:so + ss])
    m.trail = bytes(b[so + ss:])
    return m


def write(m, be):
    E = '>' if be else '<'
    po = 0x70
    params = b''.join(struct.pack(E + 'I', h) + bytes([k, x]) + struct.pack(E + 'HHH', a1, a2, a3) for h, k, x, a1, a2, a3 in m.params)
    ho = po + len(params) + len(m.gap1)
    hashes = struct.pack(E + '%dI' % len(m.hashes), *m.hashes)
    so = ho + len(hashes) + len(m.gap2)
    out = bytearray()
    out += struct.pack(E + 'IHH', m.magic, m.ver, m.ver2)
    out += struct.pack(E + 'II', m.a, m.b) + m.zero10 + struct.pack(E + 'II', m.c, m.d)
    for s, f, t, tail in m.passes:
        out += struct.pack(E + 'III', s, f, t) + tail
    out += struct.pack(E + '8H', m.table[0], len(m.params), po, len(params), ho, len(hashes), so, len(m.strings))
    out += m.zero64 + params + m.gap1 + hashes + m.gap2 + m.strings + m.trail
    return bytes(out)
