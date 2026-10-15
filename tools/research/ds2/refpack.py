"""EA RefPack (QFS) decompressor, used by the PC .str 'Rpak' chunks."""


def decompress(src, pos=0):
    flags = src[pos]
    if src[pos + 1] != 0xFB:
        raise ValueError('not RefPack (no 0xFB marker)')
    i = pos + 2
    n = 4 if flags & 0x80 else 3
    if flags & 0x01:
        i += n  # compressed size, not needed
    usize = int.from_bytes(src[i:i + n], 'big')
    i += n
    out = bytearray()
    while True:
        b0 = src[i]
        i += 1
        if b0 < 0x80:
            b1 = src[i]; i += 1
            lit = b0 & 3
            length = ((b0 & 0x1C) >> 2) + 3
            off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[i], src[i + 1]; i += 2
            lit = b1 >> 6
            length = (b0 & 0x3F) + 4
            off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[i], src[i + 1], src[i + 2]; i += 3
            lit = b0 & 3
            length = ((b0 & 0x0C) << 6) + b3 + 5
            off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            lit = ((b0 & 0x1F) << 2) + 4
            out += src[i:i + lit]; i += lit
            continue
        else:
            lit = b0 & 3
            out += src[i:i + lit]; i += lit
            break
        out += src[i:i + lit]; i += lit
        start = len(out) - off
        if start < 0:
            raise ValueError('RefPack offset before start')
        if off >= length:
            out += out[start:start + length]
        else:
            for k in range(length):
                out.append(out[start + k])
    if len(out) != usize:
        raise ValueError('RefPack size mismatch: got %d, header says %d' % (len(out), usize))
    return bytes(out)
