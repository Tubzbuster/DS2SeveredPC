"""Learned 360 -> PC byte orders for formats made of typed blocks.

A layout function splits a 360 file into blocks (start, end, type key) and
names words that are always swapped (pointers, tables) and byte ranges kept
as stored. Each block type gets a ds2.templates.Template, with fallbacks to
coarser keys; names (printable runs ending in NUL) stay as stored.
Used by ds2/reloc.py (BNK) and ds2/hkx.py (Havok).
"""
import re
from . import templates as T

MAX_WORDS = 1 << 14
_TEXT = re.compile(rb'[A-Za-z0-9_.\-/ ]{4,}\x00')


class Layout:
    def __init__(self, blocks, swap=(), raw=(), limit=None, text=True):
        self.text = text              # keep printable names as stored
        self.blocks = blocks          # [(start, end, key)]
        self.swap = swap              # word offsets always 32-bit swapped
        self.raw = raw                # [(start, end)] kept as stored
        self.limit = limit            # text search limit


class Model:
    def __init__(self, layout, keys, q64=False):
        self.q64 = q64                # learn 8-byte values (Havok)
        self.layout = layout          # bytes -> Layout or None
        self.keys = keys              # type key -> [keys, most specific first]
        self.t = {}

    def train(self, x, p):
        lay = self.layout(x)
        if lay is None or len(x) != len(p):
            return
        for s, e, typ in lay.blocks:
            for key in self.keys(typ):
                n = min((e - s) // 4, MAX_WORDS)
                tm = self.t.get(key)
                if tm is None or tm.n < n:
                    old = tm
                    tm = T.Template(n)
                    if old:
                        for i in range(old.n):
                            tm.counts[i] = old.counts[i]
                            tm.informative[i] = old.informative[i]
                        tm.samples = old.samples
                        tm.q8[:old.n] = old.q8
                        tm.not32[:old.n] = old.not32
                    self.t[key] = tm
                tm.train(x[s:s + 4 * n], p[s:s + 4 * n])

    def finish(self):
        self.perms = {k: v.perms(swap_default_words=64, q64=self.q64) for k, v in self.t.items()}
        self.samples = {k: v.samples for k, v in self.t.items()}
        self.majority = {}
        for k, v in self.t.items():
            sw = sum(c[T.SWAP] for c in v.counts)  # noqa
            rw = sum(c[T.RAW] for c in v.counts)
            self.majority[k] = T.PERMS[T.SWAP] if sw > rw else T.PERMS[T.RAW]
        del self.t
        return self

    def template_for(self, typ):
        for key in self.keys(typ):
            if key in self.perms and self.samples.get(key, 0) >= 3:
                return key, self.perms[key]
        return None, None

    def convert(self, x, lay=None):
        lay = lay or self.layout(x)
        if lay is None:
            return None
        out = bytearray(x)
        wide = set()                  # words of 8-byte values: not text
        for s, e, typ in lay.blocks:
            key, pm = self.template_for(typ)
            if pm is None:
                continue
            n = (e - s) // 4
            if n > len(pm):
                fill = self.majority[key] if n <= 256 and key != ('any',) else T.PERMS[T.RAW]
                pm = pm + [fill] * (n - len(pm))
            out[s:s + 4 * n] = T.apply(pm[:n], x[s:s + 4 * n])
            for i in range(n):
                if pm[i] in (T.Q64, T.Q64B):
                    wide.add(s + 4 * i)
        lim = lay.limit if lay.limit is not None else len(x)
        for m in (_TEXT.finditer(x, 0, lim) if lay.text else ()):
            a, b = m.start(), m.end()
            core = x[a:b - 1].strip(b'_')
            if len(core) < 3 or sum(c >= 0x41 for c in core) < 2:
                continue
            a = a + (len(x[a:b - 1]) - len(x[a:b - 1].lstrip(b'_')))
            for w in range((a + 3) // 4 * 4, b // 4 * 4, 4):
                if w not in wide:
                    out[w:w + 4] = x[w:w + 4]
            w = b // 4 * 4
            if w not in wide and a <= w < b and all(32 <= c < 127 or c == 0 for c in x[w:w + 4]) and w + 4 <= lim \
                    and x[w + 3:w + 4] in (b'\0', b'_'):
                out[w:w + 4] = x[w:w + 4]
        for a, b in lay.raw:
            out[a:b] = x[a:b]
        for f in lay.swap:
            out[f:f + 4] = x[f:f + 4][::-1]
        return bytes(out)
