"""LH2 string tables ('2HCL' on 360, 'LCH2' on PC): header (magic, size,
flags 0x40000001, u32, string count, language count, 0, 0), sorted string
IDs, then count x languages string offsets, then the strings (raw). All
32-bit up to the strings."""
import struct


def convert(x):
    if x[:4] != b'2HCL' or len(x) < 0x20:
        return None
    n, langs = struct.unpack_from('>II', x, 0x10)
    end = 0x20 + 4 * n + 4 * n * langs
    if end > len(x):
        return None
    k = end // 4
    return struct.pack('<%dI' % k, *struct.unpack_from('>%dI' % k, x)) + x[end:]
