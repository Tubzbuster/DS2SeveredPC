"""Minimal reader for Xbox 360 STFS packages (CON / LIVE / PIRS): Severed's
addon file and 360 save games. Block maths after Velocity (GPL; reimplemented
from the format description, no code copied).

    for path, data in stfs.files(open(p, 'rb').read()): ...
"""
import struct


def _be24(b, o):
    return (b[o] << 16) | (b[o + 1] << 8) | b[o + 2]


def _le24(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


class Package:
    def __init__(self, d):
        if d[:4] not in (b'CON ', b'LIVE', b'PIRS'):
            raise ValueError('not an STFS package')
        self.d = d
        hsz = struct.unpack_from('>I', d, 0x340)[0]
        self.first = (hsz + 0xFFF) & ~0xFFF
        vd = 0x379
        self.sex = (~d[vd + 2]) & 1          # 0 female, 1 male
        self.ft_count = struct.unpack_from('<H', d, vd + 3)[0]
        self.ft_block = _le24(d, vd + 5)
        self.title_id = struct.unpack_from('>I', d, 0x360)[0]
        self.display_name = d[0x411:0x411 + 0x80].decode('utf-16-be', 'replace').split('\0')[0]

    def _data_block(self, n):
        s = self.sex
        r = (((n + 0xAA) // 0xAA) << s) + n
        if n < 0xAA:
            return r
        if n < 0x70E4:
            return r + (((n + 0x70E4) // 0x70E4) << s)
        return (1 << s) + r + (((n + 0x70E4) // 0x70E4) << s)

    def _addr(self, n):
        return (self._data_block(n) << 12) + self.first

    def _l0_hash_block(self, n):
        s = self.sex
        if n < 0xAA:
            return 0
        r = (n // 0xAA) * (0xAB if s == 0 else 0xAC)
        if n >= 0x70E4:
            r += ((n // 0x70E4) + 1) << s
        else:
            r += 1 << s
        return r

    def _next(self, n):
        hb = self._l0_hash_block(n)
        a = (hb << 12) + self.first + (n % 0xAA) * 0x18
        return _be24(self.d, a + 0x15)

    def _read(self, start, size, consecutive):
        out = bytearray()
        n = start
        while len(out) < size:
            a = self._addr(n)
            out += self.d[a:a + 0x1000]
            n = n + 1 if consecutive else self._next(n)
        return bytes(out[:size])

    def entries(self):
        ft = self._read(self.ft_block, self.ft_count * 0x1000, True) if self.ft_count else b''
        out = []
        for o in range(0, len(ft), 0x40):
            e = ft[o:o + 0x40]
            if e[0] == 0:
                break
            fl = e[0x28]
            out.append(dict(name=e[:fl & 0x3F].decode('latin1'), dir=bool(fl & 0x80), consecutive=bool(fl & 0x40),
                            start=_le24(e, 0x2F), parent=struct.unpack_from('>h', e, 0x32)[0],
                            size=struct.unpack_from('>I', e, 0x34)[0]))
        return out

    def files(self):
        es = self.entries()

        def path(i):
            p = []
            while i >= 0:
                p.append(es[i]['name'])
                i = es[i]['parent']
            return '/'.join(reversed(p))
        for i, e in enumerate(es):
            if not e['dir']:
                yield path(i), self._read(e['start'], e['size'], e['consecutive'])


def files(d):
    return Package(d).files()
