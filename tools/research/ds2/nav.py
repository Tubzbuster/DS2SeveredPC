"""NAV navigation collections (*.navcollection.xml.xen -> .win).

All 32-bit except: a constant 128-byte table (always the same bytes; kept
as stored), unused pointer slots (0xFFFFFFFF followed by 2 or 0x1B: 0 on
PC; 1,607 of 1,607 in the pairs), and a per-collection hash (header 0x34
and nested headers): the sum of the blob's data as big-endian 32-bit
words, checked by the game when it adds the blob to the nav world (exe
0x5BB980 via 0x5BADE0); a blob whose sum is wrong is dropped, leaving the
AI without navigation. Recomputed over the converted bytes (see checksums).

Asset IDs: PC names end in .win instead of .xen; id1-3 = id + sdbm delta of
the two names, id4 = id4 - 1 (see pc_ids).
"""
import struct

SIGNATURE = bytes.fromhex('bf14d67e2ddc8e6683ef574961ff698f')
TABLE_SIZE = 128
M = 0xFFFFFFFF


def convert(x):
    n = len(x) // 4
    w = struct.unpack_from('>%dI' % n, x)
    out = [v for v in w]
    for i in range(n - 1):
        if w[i] == 0xFFFFFFFF and w[i + 1] in (2, 0x1B):
            out[i] = 0
    b = bytearray(struct.pack('<%dI' % n, *out)) + x[4 * n:]
    i = x.find(SIGNATURE)
    while i >= 0:
        b[i:i + TABLE_SIZE] = x[i:i + TABLE_SIZE]
        i = x.find(SIGNATURE, i + TABLE_SIZE)
    checksums(x, b)
    return bytes(b)


HEADER = 0x18  # u32 endian marker, version 2, size, sum, flags, ?


def _sum(b, o, n):
    n &= ~3
    return sum(struct.unpack_from('>%dI' % (n // 4), b, o)) & M


def headers(x):
    """offsets of the blob headers in 360 data (their sums verify)"""
    found = []
    for p in range(0, len(x) - HEADER + 1, 4):
        mark, ver, size, s = struct.unpack_from('>4I', x, p)
        if mark == M and ver == 2 and 0 < size <= len(x) - p - HEADER \
                and _sum(x, p + HEADER, size) == s:
            found.append(p)
    return found


def checksums(x, b):
    """recompute each header's sum over the converted data, innermost first"""
    for p in sorted(headers(x), reverse=True):
        size = struct.unpack_from('<I', b, p + 8)[0]
        struct.pack_into('<I', b, p + 12, _sum(b, p + HEADER, size))


def _sdbm(s, h=0):
    for c in s:
        h = (h * 65599 + c) & M
    return h


def pc_name(name):
    return name[:-4] + '.win' if name.lower().endswith('.xen') else name


def pc_ids(name, ids):
    """PC asset IDs from the 360 ones (verified on the pairs)"""
    d = (_sdbm(pc_name(name).encode()) - _sdbm(name.encode())) & M
    return (ids[0], (ids[1] + d) & M, (ids[2] + d) & M, (ids[3] + d) & M, (ids[4] - 1) & M)
