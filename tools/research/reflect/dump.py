"""Reads probe v6's severed_desc.bin (chunks of the running game's memory)
together with the exe's .rdata (strings), and decodes the engine's class
descriptors.

    D = Dump(desc_bin, exe).descriptors()   # {va: (kind, name, words[24])}
"""
import struct, bisect

CLASS_VT, FLAGS_VT, ENUM_VT = 0x1B1E648, 0x1AA6C80, 0x1AA6C68
KINDS = {CLASS_VT: 'class', FLAGS_VT: 'flags', ENUM_VT: 'enum'}
DATA, DATA_SIZE = 0x1C30000, 0x528000


class Dump:
    def __init__(self, desc_bin, exe):
        b = open(desc_bin, 'rb').read()
        if b[:7] not in (b'SVDESC5', b'SVDESC6'):
            raise ValueError('not a probe descriptor dump')
        self.chunks = []
        o = 8
        while o + 8 <= len(b):
            va, n = struct.unpack_from('<II', b, o)
            self.chunks.append((va, b[o + 8:o + 8 + n]))
            o += 8 + n
        self.chunks.sort(key=lambda c: c[0])
        self.starts = [c[0] for c in self.chunks]
        e = open(exe, 'rb').read()
        pe = struct.unpack_from('<I', e, 0x3C)[0]
        nsec = struct.unpack_from('<H', e, pe + 6)[0]
        opt = struct.unpack_from('<H', e, pe + 20)[0]
        base = struct.unpack_from('<I', e, pe + 52)[0]
        self.rdata = None
        for i in range(nsec):
            s = pe + 24 + opt + 40 * i
            if e[s:s + 8].rstrip(b'\0') == b'.rdata':
                vs, va, rs, ra = struct.unpack_from('<IIII', e, s + 8)
                self.rdata = (base + va, e[ra:ra + rs])

    def read(self, va, n):
        if va is None:
            return None
        rva, rb = self.rdata
        if rva <= va < rva + len(rb):
            return rb[va - rva:va - rva + n]
        i = bisect.bisect_right(self.starts, va) - 1
        while i >= 0:
            s, d = self.chunks[i]
            if s <= va and va + n <= s + len(d):
                return d[va - s:va - s + n]
            if s + len(d) < va:
                break
            i -= 1
        return None

    def u32(self, va):
        x = self.read(va, 4)
        return struct.unpack('<I', x)[0] if x else None

    def cstr(self, va):
        for n in (160, 64, 32, 16, 8):
            x = self.read(va, n)
            if x:
                e = x.find(b'\0')
                if e >= 0 and all(32 <= c < 127 for c in x[:e]):
                    return x[:e].decode('latin1')
                return None
        return None

    def in_rdata(self, va):
        return self.rdata[0] <= va < self.rdata[0] + len(self.rdata[1])

    def descriptors(self):
        out = {}
        for s, d in self.chunks:
            if not DATA <= s < DATA + DATA_SIZE:
                continue
            n = len(d) // 4
            w = struct.unpack('<%dI' % n, d[:4 * n])
            for j in range(n - 1):
                if w[j] in KINDS and self.in_rdata(w[j + 1]):
                    va = s + 4 * j
                    out[va] = (KINDS[w[j]], self.cstr(w[j + 1]), [self.u32(va + 4 * k) for k in range(24)])
        return out

    def fields(self, words):
        """[(offset, type, field name, type-info va, flags/enum va)] or None"""
        n = words[17] & 0xFFFF
        out = []
        for i in range(n):
            r = self.read(words[10] + 16 * i, 16) if words[10] else None
            if r is None:
                return None
            ti, fd, off, idx, _, _ = struct.unpack('<IIHHHH', r)
            name = self.cstr(self.u32(fd))
            typ = self.u32(fd + 8)
            if name is None or typ is None:
                return None
            out.append((off, typ, name, ti, self.u32(fd + 12)))
        return out
