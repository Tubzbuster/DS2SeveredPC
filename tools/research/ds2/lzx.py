"""LZX decoder for Xbox 360 XMemCompress data (the 'LZXD' chunks in .str files).

Port of the LZX algorithm as implemented in libmspack's lzxd.c, with the
XMemCompress "native" framing on top: each frame is
    [FF uu uu cc cc] or [cc cc]   (u16 big-endian sizes)
followed by cc compressed bytes, producing uu (default 0x8000) output bytes.
Decoder state (trees, repeat offsets, window) carries across frames; the bit
reader restarts at each frame's first byte.
"""

MIN_MATCH = 2
NUM_CHARS = 256
PRETREE_NUM = 20
ALIGNED_NUM = 8
LENGTH_NUM = 249
FRAME_SIZE = 0x8000

_EXTRA = []
_j = 0
for _i in range(0, 52, 2):
    _EXTRA += [_j, _j]
    if _i != 0 and _j < 17:
        _j += 1
_BASE = [0]
for _i in range(51):
    _BASE.append(_BASE[-1] + (1 << _EXTRA[_i]))
_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}


class LZXError(Exception):
    pass


class _Huff:
    """Canonical Huffman decoding table (MSB-first codes)."""

    def __init__(self, lens):
        self.max = max(lens) if lens else 0
        if self.max == 0:
            self.table = None
            return
        self.lens = lens
        # Build a full lookup table of 2^max entries: (symbol, length).
        size = 1 << self.max
        table = [None] * size
        code = 0
        for bits in range(1, self.max + 1):
            for sym, l in enumerate(lens):
                if l == bits:
                    start = code << (self.max - bits)
                    end = start + (1 << (self.max - bits))
                    if end > size:
                        raise LZXError('over-subscribed Huffman table')
                    entry = (sym, bits)
                    for k in range(start, end):
                        table[k] = entry
                    code += 1
            code <<= 1
        self.table = table


class _Bits:
    __slots__ = ('data', 'pos', 'end', 'buf', 'left')

    def __init__(self, data, pos, end):
        self.data, self.pos, self.end = data, pos, end
        self.buf = 0
        self.left = 0

    def _word(self):
        if self.pos + 1 < self.end:
            w = self.data[self.pos] | (self.data[self.pos + 1] << 8)
        else:
            w = 0  # read past the frame: zeros, as libmspack does
        self.pos += 2
        self.buf |= w << (16 - self.left)  # buffer holds bits MSB-first in a 32-bit field
        self.left += 16

    def ensure(self, n):
        while self.left < n:
            self._word()

    def peek(self, n):
        self.ensure(n)
        return (self.buf >> (32 - n)) & ((1 << n) - 1)

    def remove(self, n):
        self.buf = (self.buf << n) & 0xFFFFFFFF
        self.left -= n

    def read(self, n):
        if n == 0:
            return 0
        v = self.peek(n)
        self.remove(n)
        return v

    def sym(self, h):
        if h.table is None:
            raise LZXError('empty Huffman tree used')
        self.ensure(16)  # libmspack always tops up to 16 bits here; this matters for uncompressed blocks
        sym, l = h.table[(self.buf >> (32 - h.max)) & ((1 << h.max) - 1)]
        self.remove(l)
        return sym


class LZXDecoder:
    def __init__(self, window_bits=17):
        if window_bits not in _SLOTS:
            raise ValueError('bad window size')
        self.slots = _SLOTS[window_bits]
        self.main_lens = [0] * (NUM_CHARS + self.slots * 8)
        self.len_lens = [0] * LENGTH_NUM
        self.R = [1, 1, 1]
        self.header_read = False
        self.block_type = 0
        self.block_remaining = 0
        self.block_length = 0
        self.main = self.length = self.aligned = None
        self.out = bytearray()
        self.total = 0
        self.e8 = False

    def _read_lens(self, bits, lens, first, last):
        pre = [bits.read(4) for _ in range(PRETREE_NUM)]
        pt = _Huff(pre)
        x = first
        while x < last:
            z = bits.sym(pt)
            if z == 17:
                n = bits.read(4) + 4
                lens[x:x + n] = [0] * n
                x += n
            elif z == 18:
                n = bits.read(5) + 20
                lens[x:x + n] = [0] * n
                x += n
            elif z == 19:
                n = bits.read(1) + 4
                z = bits.sym(pt)
                v = (lens[x] - z) % 17
                lens[x:x + n] = [v] * n
                x += n
            else:
                lens[x] = (lens[x] - z) % 17
                x += 1

    def decode_frame(self, data, pos, end, frame_out):
        """Decode one frame of compressed bytes data[pos:end] into frame_out bytes."""
        bits = _Bits(data, pos, end)
        out = self.out
        target = self.total + frame_out
        self.total = target
        if not self.header_read:
            if bits.read(1):
                hi = bits.read(16); lo = bits.read(16)
                self.e8 = (hi << 16 | lo) != 0
                if self.e8:
                    raise LZXError('Intel E8 translation not implemented')
            self.header_read = True
        R = self.R
        while len(out) < target:
            if self.block_remaining == 0:
                if self.block_type == 3 and (self.block_length & 1):
                    bits.pos += 1  # pad byte after odd-length uncompressed block
                self.block_type = bits.read(3)
                self.block_length = self.block_remaining = (bits.read(16) << 8) | bits.read(8)
                if self.block_type == 2:
                    self.aligned = _Huff([bits.read(3) for _ in range(ALIGNED_NUM)])
                if self.block_type in (1, 2):
                    ml = self.main_lens
                    self._read_lens(bits, ml, 0, NUM_CHARS)
                    self._read_lens(bits, ml, NUM_CHARS, NUM_CHARS + self.slots * 8)
                    self.main = _Huff(ml)
                    self._read_lens(bits, self.len_lens, 0, LENGTH_NUM)
                    self.length = _Huff(self.len_lens)
                elif self.block_type == 3:
                    # align to 16 bits exactly as libmspack does: drop the bit buffer
                    if bits.left == 0:
                        bits.ensure(16)
                    bits.buf = 0
                    bits.left = 0
                    r = data[bits.pos:bits.pos + 12]
                    bits.pos += 12
                    R[0] = int.from_bytes(r[0:4], 'little')
                    R[1] = int.from_bytes(r[4:8], 'little')
                    R[2] = int.from_bytes(r[8:12], 'little')
                else:
                    raise LZXError('bad block type %d' % self.block_type)

            run = min(self.block_remaining, target - len(out))
            if self.block_type == 3:
                out += data[bits.pos:bits.pos + run]
                bits.pos += run
                self.block_remaining -= run
                continue
            aligned = self.block_type == 2
            produced = 0
            while produced < run:
                e = bits.sym(self.main)
                if e < NUM_CHARS:
                    out.append(e)
                    produced += 1
                    continue
                e -= NUM_CHARS
                ml = e & 7
                if ml == 7:
                    ml += bits.sym(self.length)
                ml += MIN_MATCH
                slot = e >> 3
                if slot == 0:
                    off = R[0]
                elif slot == 1:
                    off = R[1]; R[1] = R[0]; R[0] = off
                elif slot == 2:
                    off = R[2]; R[2] = R[0]; R[0] = off
                else:
                    extra = 17 if slot >= 36 else _EXTRA[slot]
                    off = _BASE[slot] - 2
                    if not aligned:
                        if slot == 3:
                            off = 1
                        else:
                            off += bits.read(extra)
                    else:
                        if extra > 3:
                            off += bits.read(extra - 3) << 3
                            off += bits.sym(self.aligned)
                        elif extra == 3:
                            off += bits.sym(self.aligned)
                        elif extra > 0:
                            off += bits.read(extra)
                        else:
                            off = 1
                    R[2] = R[1]; R[1] = R[0]; R[0] = off
                if off > len(out):
                    raise LZXError('match offset %d before start of data' % off)
                start = len(out) - off
                if off >= ml:
                    out += out[start:start + ml]
                else:
                    for k in range(ml):
                        out.append(out[start + k])
                produced += ml
            self.block_remaining -= produced
            if self.block_remaining < 0:
                raise LZXError('match ran past end of block')
        return target


def xmem_decompress(data, usize, window_bits=17):
    """Decompress XMemCompress native frames in `data` to `usize` bytes."""
    dec = LZXDecoder(window_bits)
    pos = 0
    produced = 0
    while produced < usize and pos < len(data):
        if data[pos] == 0xFF:
            fu = (data[pos + 1] << 8) | data[pos + 2]
            fc = (data[pos + 3] << 8) | data[pos + 4]
            pos += 5
        else:
            fu = FRAME_SIZE
            fc = (data[pos] << 8) | data[pos + 1]
            pos += 2
        if fc == 0:
            break
        fu = min(fu, usize - produced)
        dec.decode_frame(data, pos, pos + fc, fu)
        produced += fu
        pos += fc
    return bytes(dec.out[:usize])
