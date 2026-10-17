"""Sound banks (.sbk, 'sbnk' v209): 360 -> PC.

Layout (u32 words; 360 big-endian, PC little-endian):
  0x00 'sbnk' (byte-swapped on PC), 209, metadata size, data size,
  data offset, data size, 209, 0
  0x20 section offsets (relative to 0x18):
       0x24 A end, 0x28 N, 0x2C B, 0x30 C, 0x34 ?, 0x38 E, 0x3C E size,
       0x40 G, 0x44 H, 0x48 N, 0x4C N, 0x50 0, 0x54 bank hash
  0x68     N offsets of the A records (relative to the end of that list)
  A        records; words +4 and +0x1C are byte-packed (kept raw)
  B        N offsets of the C records
  C .. E   float tables; each starts with a u16 count (u16 pair swapped)
  E        8-byte entries {u16, 2 bytes, u32}
  G        records (plain words)
  H        0x18-byte entries; the last word is a hash stored byte-reversed
           (identical bytes on both platforms)
  data     'sdat', count, count x {index, 0x0313BABE, offset, 0xFEEDFEED},
           then the samples back to back: EAAudioCore header + one block
           (flag 0; two, split at the loop start, when a loop starts
           mid-sample). 360 codec 3 (EA-XMA); written as codec 4 (EA-XAS),
           which the PC engine decodes for its streams.

Checked against 80 PC/360 bank pairs: metadata identical apart from the
data size and (in 2 banks built from different sample sets) sample
indices."""
import struct
from . import eaaudio as A

SWAP, RAW, U16, U16A = range(4)


def _perm(kind, w):
    if kind == SWAP:
        return w[::-1]
    if kind == RAW:
        return w
    if kind == U16:
        return w[1::-1] + w[:1:-1]
    return w[1::-1] + w[2:]


def word_kinds(x):
    """byte order of each metadata word (360 data)"""
    W = lambda o: struct.unpack_from('>I', x, o)[0]
    mo = W(0x10)
    n = W(0x28)
    a_end, b, c, e, e_size, g, h = (W(o) + 0x18 if o != 0x3C else W(o)
                                    for o in (0x24, 0x2C, 0x30, 0x38, 0x3C, 0x40, 0x44))
    kinds = [SWAP] * (mo // 4)
    a0 = 0x68 + 4 * n
    for i in range(n):
        r = a0 + W(0x68 + 4 * i)
        for off in (4, 0x1C):
            if r + off < a_end:
                kinds[(r + off) // 4] = RAW
    for o in range(c, min(e, mo), 4):
        v = W(o)
        if v & 0xFFFF == 0 and 0 < v >> 16 < 0x100:
            kinds[o // 4] = U16
    for o in range(e, min(e + e_size, mo), 8):
        kinds[o // 4] = U16A
    for o in range(h + 20, mo, 0x18):
        kinds[o // 4] = RAW
    return kinds


def convert_meta(x):
    mo = struct.unpack_from('>I', x, 0x10)[0]
    out = bytearray(mo)
    for i, k in enumerate(word_kinds(x)):
        out[4 * i:4 * i + 4] = _perm(k, x[4 * i:4 * i + 4])
    return out


def samples(b, endian='>'):
    """[(index, sample bytes)] from the sdat section"""
    o = struct.unpack_from(endian + 'I', b, 0x10)[0]
    assert b[o:o + 4] in (b'sdat', b'tads')
    n = struct.unpack_from(endian + 'I', b, o + 4)[0]
    ents = [struct.unpack_from(endian + '4I', b, o + 8 + 16 * i) for i in range(n)]
    offs = sorted({off for _, _, off, _ in ents}) + [len(b) - o]
    # samples sit back to back; a long one spans several blocks
    return [(idx, b[o + off:o + offs[offs.index(off) + 1]]) for idx, _, off, _ in ents]


def build_data(smp):
    """sdat section (PC byte order) from [(index, sample bytes)]"""
    head = b'sdat' + struct.pack('<I', len(smp))
    off = 8 + 16 * len(smp)
    ents, body = b'', b''
    for idx, s in smp:
        ents += struct.pack('<4I', idx, 0x0313BABE, off + len(body), 0xFEEDFEED)
        body += s
    return head + ents + body


def convert_sample(s, ffmpeg=None):
    h = A.parse_header(s)
    if h['codec'] != A.CODEC_EAXMA:
        raise ValueError('codec %d' % h['codec'])
    pcm = A.decode_eaxma(A.blocks(s, h['header_size'], len(s)), h['channels'], h['rate'], h['samples'], ffmpeg)
    ls = h.get('loop_start') if h['loop'] else None
    if ls and 0 < ls < h['samples']:
        # a loop from mid-sample: the PC decoder restarts at the block that
        # begins at the loop start (none in a single block: null read,
        # exe 0x515F0F, the decompression room crash), so split it there
        n = ls * h['channels']
        body = A.xas_blocks(pcm[:n], h['channels'], single=True) + A.xas_blocks(pcm[n:], h['channels'], single=True)
    else:
        body = A.xas_blocks(pcm, h['channels'], single=True)
    hdr = A.make_header(A.CODEC_XAS1, h['channels'], h['rate'], h['samples'], type_=0,
                        loop_start=h.get('loop_start') if h['loop'] else None, version=h['version'])
    return hdr + body


def assemble(meta, data_off, data):
    out = bytearray(meta) + bytes(max(0, data_off - len(meta)))
    out = out[:data_off] + data
    struct.pack_into('<I', out, 0x0C, len(data))
    struct.pack_into('<I', out, 0x10, data_off)
    struct.pack_into('<I', out, 0x14, len(data))
    return bytes(out)


def convert(x, ffmpeg=None):
    if x[:4] != b'knbs':  # 'sbnk' as a big-endian word
        return None
    data_off = struct.unpack_from('>I', x, 0x10)[0]
    meta = convert_meta(x)
    smp = [(i, convert_sample(s, ffmpeg)) for i, s in samples(x)]
    return assemble(meta, data_off, build_data(smp))
