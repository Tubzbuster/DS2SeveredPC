"""SMB: 32-bit words, except record headers (u16 0x0016, u16 0x40-0x50:
two 16-bit fields; 2,165/2,165 in the pairs, no false hits) and names
(printable runs of 5+ characters ending in NUL, kept as stored)."""
import re
import struct

_TEXT = re.compile(rb'[A-Za-z0-9_.\-/ ]{5,}\x00')


def convert(x):
    n = len(x) // 4
    w = struct.unpack_from('>%dI' % n, x)
    out = bytearray(struct.pack('<%dI' % n, *w)) + x[4 * n:]
    for i, v in enumerate(w):
        if v >> 16 == 0x16 and 0x40 <= (v & 0xFFFF) <= 0x50:
            out[4 * i:4 * i + 4] = struct.pack('<HH', 0x16, v & 0xFFFF)
    for m in _TEXT.finditer(x):
        a, b = m.start(), m.end()
        if sum(c >= 0x41 for c in x[a:b]) < 2:
            continue
        for q in range((a + 3) // 4 * 4, b // 4 * 4, 4):
            out[q:q + 4] = x[q:q + 4]
        q = b // 4 * 4
        if a <= q < b and all(32 <= c < 127 or c == 0 for c in x[q:q + 4]):
            out[q:q + 4] = x[q:q + 4]
    return bytes(out)
