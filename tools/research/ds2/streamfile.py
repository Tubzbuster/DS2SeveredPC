"""Dead Space 2 stream files (.str): 'ols3' (Xbox 360, big-endian) and
'3slo' (PC, little-endian).

Layout: 12-byte file header, then chunks {tag, u32 size (incl. header),
...}. 'SHOC' chunks carry a sub-tag at +8:
    SHDR  asset header: type hash, flags, ids, uncompressed size, name,
          source path, type name
    SDAT  raw data (payload at +12)
    LZXD  360 XMemCompress data: u32 compressed size at +12, frames at +16
    Rpak  PC RefPack data: u32 compressed size at +12, RefPack stream at +16
'FILL' pads the file to 128 KB sectors.
"""
import struct
from . import lzx, refpack


class Asset:
    def __init__(self, offset, header, be):
        E = '>' if be else '<'
        self.offset = offset
        self.header = header
        self.be = be
        self.type_hash = struct.unpack(E + 'I', header[12:16])[0]
        self.flags = struct.unpack(E + 'HH', header[16:20])
        self.ids = struct.unpack(E + 'IIIII', header[20:40])
        self.usize = struct.unpack(E + 'I', header[40:44])[0]
        parts = header[44:].split(b'\0')
        self.name = parts[0].decode('latin1')
        self.path = parts[1].decode('latin1') if len(parts) > 1 else ''
        self.type = parts[2].decode('latin1') if len(parts) > 2 else ''
        self.chunks = []  # (kind, chunk bytes)

    def payload(self):
        out = bytearray()
        for kind, c in self.chunks:
            if kind == 'SDAT':
                out += c[12:12 + self.usize - len(out)]  # chunk is padded to 4 bytes
            elif kind == 'LZXD':
                csize = struct.unpack('>I', c[12:16])[0]
                out += lzx.xmem_decompress(c[16:16 + csize], self.usize - len(out))
            elif kind == 'Rpak':
                out += refpack.decompress(c, 16)
            else:
                raise ValueError('unknown data chunk ' + kind)
        return bytes(out)

    def __repr__(self):
        return '<%s %s %d bytes>' % (self.type, self.name, self.usize)


def read(data):
    magic = data[:4]
    if magic == b'ols3':
        be = True
    elif magic == b'3slo':
        be = False
    else:
        raise ValueError('not a stream file')
    E = '>' if be else '<'
    o = 12
    assets = []
    cur = None
    while o + 8 <= len(data):
        tag = data[o:o + 4] if be else data[o:o + 4][::-1]
        size = struct.unpack(E + 'I', data[o + 4:o + 8])[0]
        if size == 0:
            break
        c = data[o:o + size]
        if tag == b'SHOC':
            sub = (c[8:12] if be else c[8:12][::-1]).decode('latin1')
            if sub == 'SHDR':
                cur = Asset(o, c, be)
                assets.append(cur)
            elif cur is not None:
                cur.chunks.append((sub, c))
        o += size
    return be, assets
