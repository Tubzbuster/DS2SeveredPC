"""LightTOC and VariableDictionary: 360 -> PC.

LightTOC: 16-byte header (u16 pair, u32 0x10, u32, u16 count + u16), then
count x 0xA0-byte light records:
  +0x00 two u32 hashes, +0x08 two u32 of author-ID text (e.g. 'CHERNEY8',
  stored as words like Graph's header), +0x10 4x4 float matrix, +0x50 u32,
  +0x54 two bytes then a u16, +0x58 u32, +0x5C colour bytes, +0x60 u32,
  +0x64 seven floats, +0x80 four bytes, +0x84 28-byte name.
Checked against the one PC/360 pair (different light sets, same layout).

VariableDictionary: u32 4, u32 count, count x {hash, u32, u32, u32 string
offset}, then the strings.
"""
import struct

REC = 0xA0


def _sw(x, out, a, b):
    for o in range(a, b, 4):
        out[o:o + 4] = x[o:o + 4][::-1]


def _u16(x, out, a, b):
    for o in range(a, b, 2):
        out[o:o + 2] = x[o:o + 2][::-1]


def light_toc(x):
    n = struct.unpack_from('>H', x, 0x0C)[0]
    if len(x) != 16 + n * REC:
        return None
    out = bytearray(x)
    _u16(x, out, 0, 4)
    _sw(x, out, 4, 12)
    _u16(x, out, 12, 16)
    for i in range(n):
        r = 16 + i * REC
        _sw(x, out, r, r + 0x54)
        _u16(x, out, r + 0x56, r + 0x58)
        _sw(x, out, r + 0x58, r + 0x5C)
        _sw(x, out, r + 0x60, r + 0x80)
    return bytes(out)


def variable_dictionary(x):
    n = struct.unpack_from('>I', x, 4)[0]
    if 8 + 16 * n > len(x):
        return None
    out = bytearray(x)
    _sw(x, out, 0, 8 + 16 * n)
    return bytes(out)
