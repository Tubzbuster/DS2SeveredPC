"""EA VP6 videos (movies/<lang>/*.vp6): little-endian chunks ('MVhd' header,
'MV0K'/'MV0F' video frames) with an EA audio stream ('SCHl' header,
'SCCl' chunk count, 'SCDl' data, 'SCEl' end).

Severed's videos carry EA ADPCM revision 3 audio, the big-endian form: the
'SCHl' version tag (0x80) is 3, and each 'SCDl' starts with its sample count
and per-channel data offsets as big-endian words ('SCCl' holds its count
big-endian too). Revision 2 is the same data with those words
little-endian; the frames themselves (nibbles, and raw 0xEE frames in
big-endian) are identical. Which form the PC game uses is read from one
of its own videos (layout) and Severed's are rewritten to match (convert).
"""
import struct


def chunks(x):
    o = 0
    while o + 8 <= len(x):
        n = struct.unpack_from('<I', x, o + 4)[0]
        if n < 8 or o + n > len(x):
            return
        yield x[o:o + 4], o, n
        o += n


def _tags(x, o, n):
    """'SCHl' tags: {tag: (value offset, length)}"""
    p = o + 8
    if x[p:p + 4] in (b'GSTR', b'PT\0\0'):
        p += 8 if x[p:p + 4] == b'GSTR' else 4
    out = {}
    while p < o + n:
        t = x[p]
        p += 1
        if t == 0xFF:
            break
        if t in (0xFC, 0xFD, 0xFE):
            continue
        ln = x[p]
        out[t] = (p + 1, ln)
        p += 1 + ln
    return out


def _channels(x, tags):
    o, ln = tags.get(0x82, (None, 0))
    return int.from_bytes(x[o:o + ln], 'big') if o else 1


def layout(x):
    """(audio version, SCDl words little-endian, SCCl count little-endian),
    or None without EA audio"""
    version = scdl_le = sccl_le = None
    sccl = None
    for tag, o, n in chunks(x):
        if tag == b'SCHl':
            t = _tags(x, o, n)
            if 0x80 in t:
                version = x[t[0x80][0]]
        elif tag == b'SCCl':
            sccl = x[o + 8:o + 12]
        elif tag == b'SCDl':
            if scdl_le is None:
                be, le = struct.unpack_from('>I', x, o + 8)[0], struct.unpack_from('<I', x, o + 8)[0]
                scdl_le = le < be
    if version is None:
        return None
    if sccl is not None:          # a count: the reading that gives the smaller number
        sccl_le = struct.unpack('<I', sccl)[0] < struct.unpack('>I', sccl)[0]
    return version, scdl_le, sccl_le


def convert(x, target):
    """rewrite the audio of x to the target layout (from layout()); the
    video chunks are left as they are"""
    src = layout(x)
    if src is None or target is None or src == target:
        return x
    version, scdl_le, sccl_le = target
    out = bytearray(x)
    channels = 1
    for tag, o, n in chunks(x):
        if tag == b'SCHl':
            t = _tags(x, o, n)
            channels = _channels(x, t)
            if 0x80 in t and version is not None:
                out[t[0x80][0]] = version
        elif tag == b'SCCl' and sccl_le is not None and sccl_le != src[2]:
            out[o + 8:o + 12] = x[o + 8:o + 12][::-1]
        elif tag == b'SCDl' and scdl_le != src[1]:
            for w in range(o + 8, o + 12 + 4 * channels, 4):   # count, offsets
                out[w:w + 4] = x[w:w + 4][::-1]
    return bytes(out)
