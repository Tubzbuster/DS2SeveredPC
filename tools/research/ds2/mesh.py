"""Mesh ('EAGM') structure: header with a platform field (360: 1, PC: 3),
a vertex-format word at 0x38, and a stream table (offset at header 0x68)
of 16-byte entries: u32 size, u32 count, u16 stride + u8 type + u8 flags,
u32 offset."""
import struct


def streams(x, be=True):
    E = '>' if be else '<'
    so = struct.unpack_from(E + 'I', x, 0x68)[0]
    end = struct.unpack_from(E + 'I', x, 0x6C)[0]
    out = []
    for o in range(so, end, 16):
        size, count = struct.unpack_from(E + 'II', x, o)
        if be:
            stride, typ, flags = struct.unpack_from('>HBB', x, o + 8)
        else:
            stride, typ, flags = struct.unpack_from('<HBB', x, o + 8)
        off = struct.unpack_from(E + 'I', x, o + 12)[0]
        out.append({'size': size, 'count': count, 'stride': stride, 'type': typ, 'flags': flags, 'offset': off, 'entry': o})
    return out


def dec3n(w):
    out = []
    for sh in (0, 10, 20):
        c = (w >> sh) & 1023
        out.append((c - 1024 if c >= 512 else c) / 511.0)
    return out, w >> 30


def header_end(x, be=True):
    """End of the fixed header: the stream table's end, rounded to 0x80."""
    E = '>' if be else '<'
    end = struct.unpack_from(E + 'I', x, 0x6C)[0]
    return (end + 0x7F) // 0x80 * 0x80
