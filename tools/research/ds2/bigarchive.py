"""DS2DAT<n>.DAT archives ('BIGH'): what the game opens at startup.

  'BIGH', u32 LE total size, u32 BE entry count, u32 BE header size,
  count x {u32 BE offset, u32 BE size, u32 BE name hash} sorted by hash,
  trailer (copied from the game's own archives), then each file at a
  0x800-aligned offset. Name hash: sdbm (h = h * 65599 + c) of the
  lower-case path with backslashes, e.g. 'frontend\\frontend.toc'.
A later archive overrides files of an earlier one with the same hash
(checked in game with tools/archive/New-TestArchive.ps1).
"""
import struct

ALIGN = 0x800


def name_hash(name):
    h = 0
    for c in name.lower().replace('/', '\\').encode('ascii'):
        h = (h * 65599 + c) & 0xFFFFFFFF
    return h


def read_index(f):
    """{hash: (offset, size)} and the trailer of an archive file object"""
    f.seek(0)
    h = f.read(16)
    if h[:4] != b'BIGH':
        raise ValueError('not a BIGH archive')
    count, hsz = struct.unpack('>II', h[8:16])
    d = f.read(12 * count)
    idx = {}
    for i in range(count):
        off, size, hh = struct.unpack_from('>III', d, 12 * i)
        idx.setdefault(hh, (off, size))
    return idx, f.read(hsz - 16 - 12 * count)


def write(path, files, trailer=bytes(8), raw=None):
    """files: [(archive name, source path or bytes)]; raw: {name: hash} for
    entries known only by their hash"""
    raw = raw or {}
    ents = sorted(((raw[n] if n in raw else name_hash(n), n, src) for n, src in files), key=lambda e: e[0])
    hashes = [e[0] for e in ents]
    if len(set(hashes)) != len(hashes):
        raise ValueError('duplicate names')

    def size_of(src):
        if isinstance(src, (bytes, bytearray)):
            return len(src)
        import os
        return os.path.getsize(src)

    hsz = 16 + 12 * len(ents) + len(trailer)
    pos = -(-hsz // ALIGN) * ALIGN
    layout = []
    for h, n, src in ents:
        s = size_of(src)
        layout.append((h, pos, s, src))
        pos = -(-(pos + s) // ALIGN) * ALIGN
    if pos > 0xFFFFFFFF:
        raise ValueError('archive would exceed 4 GB')
    head = b'BIGH' + struct.pack('<I', pos) + struct.pack('>II', len(ents), hsz)
    head += b''.join(struct.pack('>III', off, s, h) for h, off, s, _ in layout) + trailer
    with open(path, 'wb') as out:
        out.write(head)
        for h, off, s, src in layout:
            out.write(bytes(off - out.tell()))
            if isinstance(src, (bytes, bytearray)):
                out.write(src)
            else:
                with open(src, 'rb') as f:
                    while True:
                        b = f.read(1 << 20)
                        if not b:
                            break
                        out.write(b)
        out.write(bytes(pos - out.tell()))
    return [(n, h) for h, n, _ in ents]
