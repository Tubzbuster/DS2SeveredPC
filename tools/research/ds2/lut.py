"""Colour-grading LUTs (textures named lut*): 360 -> PC.

The 360 stores a 32x32x32 RGB LUT as a 2D A8 texture of 768x128: three
256x128 planes side by side, one per output channel (R, G, B). Entry
(r, g, b) is at x = r + 32 * (b % 8), y = g + 32 * (b // 8) of each plane
(verified on the 360 identity LUT `lutcolor_default`: all 98,304 bytes).

The PC stores a 3D RGBX8 texture of 32x32x32 (131,072 bytes) whose header
carries a '3d' attribute (header conversion exact on the 37 LUT pairs).
The shader looks a colour up as (u, v, w) = (r, g, b), so in an identity
LUT the byte that follows axis x holds R, y holds G, z holds B. The byte
order is read from the PC game's own identity LUT when available
(`order_from_identity`); otherwise D3D's X8R8G8B8 (B, G, R, X in memory).
"""
import struct

N = 32
SIZE_360 = 768 * 128
SIZE_PC = N * N * N * 4
FMT, THREE_D, SIZE_ATTR = 0xDEBA72DF, 0x97CA47AB, 0x4F8B2A9F
X8R8G8B8 = (2, 1, 0, None)           # channel of each texel byte: B G R X


def _be32(x, o):
    return struct.unpack_from('>I', x, o)[0]


def is_lut_header(x):
    """a 360 LUT texture header: attributes (format 'A8', size), 768x128"""
    if len(x) < 0x30 or x[0x27] != 2:
        return False
    tab, ent = _be32(x, 0x28), _be32(x, 0x2C)
    if tab + 8 > len(x) or ent + 10 > len(x):
        return False
    if [_be32(x, tab), _be32(x, tab + 4)] != [FMT, SIZE_ATTR] or x[ent] != 0:
        return False
    s = _be32(x, ent + 1)
    return x[s:s + 3] == b'A8\0' and struct.unpack_from('>HH', x, 0x20) == (768, 128)


def header(x):
    """360 LUT texture header -> PC 3D RGBX8 header (None if not a LUT)"""
    if not is_lut_header(x):
        return None
    tail = x[_be32(x, 0):]                    # the name strings
    attrs = [(FMT, 0, b'RGBX8\0'), (THREE_D, 0, b'3d\0'), (SIZE_ATTR, 1, SIZE_PC)]
    tab = 0x30
    ent = tab + 4 * len(attrs)
    sp = ent + 5 * len(attrs)
    strings = entries = b''
    for h, kind, v in attrs:
        if kind == 0:
            entries += bytes([0]) + struct.pack('<I', sp + len(strings))
            strings += v
        else:
            entries += bytes([1]) + struct.pack('<I', v)
    start = sp + len(strings)
    d = start - _be32(x, 0)
    o = bytearray()
    o += struct.pack('<I', start) + bytes([x[4], 0]) + struct.pack('<H', struct.unpack_from('>H', x, 6)[0])
    for off in (8, 0xC, 0x10, 0x14):
        o += struct.pack('<I', _be32(x, off))
    o += struct.pack('<II', _be32(x, 0x18) + d, SIZE_PC)
    o += struct.pack('<HH', N, N) + bytes([0, 0, N, len(attrs)]) + struct.pack('<II', tab, ent)
    for h, _, _ in attrs:
        o += struct.pack('<I', h)
    return bytes(o + entries + strings + tail)


def order_from_identity(pc):
    """the channel (0 R / x, 1 G / y, 2 B / z, None pad) of each byte of a
    texel, read from the PC identity LUT; None if pc is not one"""
    if len(pc) != SIZE_PC:
        return None
    order = []
    for k in range(4):
        v = [pc[4 * t + k] for t in (0, 1, N, N * N)]
        order.append(0 if v[1] != v[0] else 1 if v[2] != v[0] else 2 if v[3] != v[0] else None)
    if sorted(c for c in order if c is not None) != [0, 1, 2]:
        return None
    for t in range(0, N * N * N, 37):         # every channel byte matches its coordinate
        pos = (t % N, t // N % N, t // (N * N))
        for k, c in enumerate(order):
            if c is not None and round(pc[4 * t + k] * (N - 1) / 255) != pos[c]:
                return None
    return tuple(order)


def data(x, order=X8R8G8B8):
    """360 LUT data (98,304 bytes) -> PC 3D texel data (131,072 bytes)"""
    if len(x) != SIZE_360:
        return None
    out = bytearray(SIZE_PC)
    for t in range(N * N * N):
        r, g, b = t % N, t // N % N, t // (N * N)
        base = (g + N * (b // 8)) * 768 + r + N * (b % 8)
        for k, c in enumerate(order):
            out[4 * t + k] = 0xFF if c is None else x[base + c * 256]
    return bytes(out)
