"""Level tables of contents (.toc, magic 0x9CBA7B28, version 10): 360 -> PC.

  0x00 magic, version, u16 stream count N, u16 name count M, u16, u16
  0x10 N x 20-byte stream entries: u32 offset of its name entry, u32 total
       uncompressed size of the stream (sum of its assets' sizes), 4 bytes
       (byte fields, same order on both platforms), u32, u32 offset of a
       list of name-entry offsets (dependencies)
  name entries (at entry 0's first word): M x {u32 name hash, u32 string
       offset}, sorted by hash
  then the dependency lists (u32 offsets), then the names (text), zero
  padding to 2 KB.

Everything is 32-bit except the u16 pair at 0x08, the byte fields and the
text. The sizes are rewritten from the converted streams when known.
"""
import struct


def _swap(x, out, a, b):
    for o in range(a, b - 3, 4):
        out[o:o + 4] = x[o:o + 4][::-1]


def parse(x, E='>'):
    W = lambda o: struct.unpack_from(E + 'I', x, o)[0]
    n, m = struct.unpack_from(E + 'HH', x, 8)
    ents = [struct.unpack_from(E + 'II4sII', x, 0x10 + 20 * i) for i in range(n)]
    names_at = ents[0][0]
    names = [struct.unpack_from(E + 'II', x, names_at + 8 * i) for i in range(m)]
    text = min(s for _, s in names)

    def name(o):
        return x[o:x.index(b'\0', o)].decode('latin1')
    return dict(n=n, m=m, ents=ents, names_at=names_at, names=names, text=text,
                stream_names=[name(W(e[0] + 4)) for e in ents])


def convert(x, sizes=None):
    """sizes: {stream name: total uncompressed size} to rewrite"""
    if x[:4] != b'\x9c\xba\x7b\x28':
        return None
    p = parse(x)
    out = bytearray(x)
    _swap(x, out, 0, 8)
    for o in range(8, 16, 2):
        out[o:o + 2] = x[o:o + 2][::-1]
    for i in range(p['n']):
        o = 0x10 + 20 * i
        _swap(x, out, o, o + 8)          # 4 bytes at +8 stay as they are
        _swap(x, out, o + 12, o + 20)
        if sizes and p['stream_names'][i] in sizes:
            struct.pack_into('<I', out, o + 4, sizes[p['stream_names'][i]])
    _swap(x, out, 0x10 + 20 * p['n'], p['text'])
    return bytes(out)
