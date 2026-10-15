"""NAV navigation collections (*.navcollection.xml.xen -> .win).

All 32-bit except: a constant 128-byte table (always the same bytes; kept
as stored), unused pointer slots (0xFFFFFFFF followed by 2 or 0x1B: 0 on
PC; 1,607 of 1,607 in the pairs), and a per-collection hash (header 0x34
and nested headers) whose PC value is computed from data we don't have:
kept (swapped). Nothing else references that hash.

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
    return bytes(b)


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
