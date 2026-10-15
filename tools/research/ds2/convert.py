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


CONVERTERS = {'LUA': lua, 'TOB': tob, 'tg4d': tg4d, 'tg4h': tg4h}
