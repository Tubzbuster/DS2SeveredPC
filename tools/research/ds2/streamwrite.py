"""Writes PC stream files ('3slo', little-endian).

Layout of the game's own stream files (both platforms): the file is read
in 128 KB sectors and no chunk crosses a sector boundary. An asset is an
SHDR chunk then its data chunks (SDAT raw, or Rpak/LZXD compressed); data
that does not fit in the rest of a sector is split into several chunks at
the boundary. A FILL chunk pads a sector when the next chunk does not fit,
and pads the last sector to its end. Chunks are padded with zeros to 4
bytes. (Same scheme as Gibbed.Visceral's StrPack, zlib licence.) The PC
reads SDAT chunks of any size alongside Rpak ones, so everything is
written uncompressed.

SHDR: alignment/flags words and IDs are the same as on 360; the source
path's '.xen' suffix becomes '.win' (NAV also renames the asset and moves
its IDs, see nav.py).
"""
import struct

SECTOR = 0x20000
FILE_HEADER = b'3slo' + struct.pack('<I', 12) + bytes((2, 0, 3, 1))


def _pad4(b):
    return b + bytes(-len(b) % 4)


def _chunk(tag, body):
    c = _pad4(tag + body)
    return b'COHS' + struct.pack('<I', len(c) + 8) + c


def shdr(type_hash, flags, ids, usize, name, path, typ):
    body = struct.pack('<I2H5II', type_hash, flags[0], flags[1], *ids, usize)
    body += b'\0'.join(s.encode('latin1') for s in (name, path, typ)) + b'\0'
    return _chunk(b'RDHS', body)


def pc_path(path):
    return path[:-4] + '.win' if path.endswith('.xen') else path


class Writer:
    def __init__(self):
        self.out = bytearray(FILE_HEADER)

    def _room(self):
        return SECTOR - len(self.out) % SECTOR

    def _fill(self):
        r = self._room()
        if r != SECTOR:
            assert r >= 8
            self.out += b'LLIF' + struct.pack('<I', r) + bytes(r - 8)

    def _put(self, c):
        r = self._room()
        if len(c) > r or r - len(c) == 4:     # a 4-byte gap cannot hold a FILL
            self._fill()
        self.out += c

    def add(self, type_hash, flags, ids, name, path, typ, payload):
        self._put(shdr(type_hash, flags, ids, len(payload), name, path, typ))
        o = 0
        while o < len(payload) or o == 0:
            r = self._room()
            if r <= 12 + 8:
                self._fill()
                r = SECTOR
            n = min(len(payload) - o, r - 12)
            if (len(payload) - o) + 12 + (-(len(payload) - o) % 4) > r:
                n = r - 12                    # split at the sector boundary
            elif r - (12 + n + (-n % 4)) == 4:
                n = r - 12 - 8                # avoid a 4-byte gap
            self._put(_chunk(b'TADS', payload[o:o + n]))
            o += n
            if not payload:
                break

    def add_asset(self, a, payload, name=None, ids=None, path=None):
        """a = streamfile.Asset (360) giving the header"""
        self.add(a.type_hash, a.flags, ids or a.ids, name if name is not None else a.name,
                 path if path is not None else pc_path(a.path), a.type, payload)

    def data(self):
        self._fill()
        return bytes(self.out)
