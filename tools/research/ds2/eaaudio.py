"""EA "EAAudioCore" sounds (SNR header + SNS blocks), as used by Dead Space 2
sound banks (.sbk samples) and streams (.snu). Format notes from vgmstream
(ISC licence, (c) Adam Gashlin, bnnm et al.); code written here.

Header (big-endian on every platform):
  word 1: version:4 codec:4 channel_config:6 (channels-1) sample_rate:18
  word 2: type:2 (0 RAM, 1 stream) loop:1 num_samples:29
  [loop start] [stream loop offset]
Blocks: u32 flag:8 (0x80 = last) size:24 (incl. this header), u32 samples,
then codec data.
  codec 3 EA-XMA (360): per 1/2-channel stream: u32 size*4 (incl. that
    word), XMA packets (0x800 each) -> standard XMA2 for ffmpeg.
  codec 4 XAS v1 (PC): per 128 samples, 0x4C bytes per channel
    (4 group headers u32 LE + 15 rows of 4 bytes).
"""
import struct, subprocess

CODEC_EAXMA, CODEC_XAS1 = 3, 4


def parse_header(b, o=0):
    h1, h2 = struct.unpack_from('>II', b, o)
    s = dict(version=h1 >> 28, codec=(h1 >> 24) & 15, channels=((h1 >> 18) & 0x3F) + 1,
             rate=h1 & 0x3FFFF, type=h2 >> 30, loop=(h2 >> 29) & 1, samples=h2 & 0x1FFFFFFF)
    size = 8
    if s['loop']:
        s['loop_start'] = struct.unpack_from('>i', b, o + 8)[0]
        size += 4
        if s['type'] == 1:
            s['loop_offset'] = struct.unpack_from('>I', b, o + 12)[0]
            size += 4
    s['header_size'] = size
    return s


def make_header(codec, channels, rate, samples, type_=0, loop_start=None, loop_offset=None, version=0):
    h1 = (version << 28) | (codec << 24) | ((channels - 1) << 18) | rate
    h2 = (type_ << 30) | ((loop_start is not None) << 29) | samples
    out = struct.pack('>II', h1, h2)
    if loop_start is not None:
        out += struct.pack('>i', loop_start)
        if type_ == 1:
            out += struct.pack('>I', loop_offset or 0)
    return out


def blocks(b, o, end=None):
    """yields (flag, samples, payload) until the last block or end"""
    end = len(b) if end is None else end
    while o + 8 <= end:
        w, n = struct.unpack_from('>II', b, o)
        flag, size = w >> 24, w & 0xFFFFFF
        if size < 8:
            break
        yield flag, n, b[o + 8:o + size]
        o += size
        if flag & 0x80:
            break


# ---- EA-XMA -> PCM (ffmpeg) -------------------------------------------------

def _xma2_riff(data, channels, rate, samples):
    fmt = struct.pack('<HHIIHHH', 0x166, channels, rate, rate * 2 * channels, 2 * channels, 16, 34)
    fmt += struct.pack('<HIIIIIIIBBH', 1, 0 if channels == 1 else 3, samples, 0x10000, 0, samples, 0, 0, 0, 4,
                       (len(data) + 0xFFFF) // 0x10000)
    riff = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', len(riff)) + riff


def eaxma_layers(blk_iter, channels):
    """raw XMA streams, one per 1/2-channel layer"""
    nl = (channels + 1) // 2
    layers = [bytearray() for _ in range(nl)]
    for flag, n, p in blk_iter:
        q = 0
        for i in range(nl):
            size = struct.unpack_from('>I', p, q)[0] // 4
            d = p[q + 4:q + size]
            layers[i] += d
            if len(d) % 0x800:
                layers[i] += b'\xff' * (0x800 - len(d) % 0x800)
            q += size
    return layers


def decode_eaxma(blk_iter, channels, rate, samples, ffmpeg='ffmpeg'):
    """interleaved int16 PCM bytes"""
    import array
    layers = eaxma_layers(blk_iter, channels)
    pcm_layers = []
    for i, d in enumerate(layers):
        lc = 1 if (i + 1 == len(layers) and channels % 2) else 2
        riff = _xma2_riff(bytes(d), lc, rate, samples)
        r = subprocess.run([ffmpeg, '-v', 'error', '-f', 'wav', '-i', '-', '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
                           input=riff, capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode()[:300])
        a = array.array('h', r.stdout)
        pcm_layers.append((lc, a))
    # interleave layers into one multichannel stream, trimmed to samples
    n = min(min(len(a) // lc for lc, a in pcm_layers), samples)
    out = array.array('h', bytes(2 * n * channels))
    c0 = 0
    for lc, a in pcm_layers:
        for c in range(lc):
            out[c0 + c::channels] = a[c:n * lc:lc]
        c0 += lc
    return out


# ---- XAS v1 -----------------------------------------------------------------

XA_COEFS = ((0.0, 0.0), (0.9375, 0.0), (1.796875, -0.8125), (1.53125, -0.859375))


def _clamp16(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else int(v)


def decode_xas_frame(fr):
    """0x4C bytes -> 128 samples (one channel)"""
    out = []
    for g in range(4):
        hdr = struct.unpack_from('<I', fr, 4 * g)[0]
        c1, c2 = XA_COEFS[hdr & 0x0F] if (hdr & 0x0F) < 4 else (0.0, 0.0)
        hist2 = struct.unpack('<h', struct.pack('<H', hdr & 0xFFF0))[0]
        hist1 = struct.unpack('<h', struct.pack('<H', (hdr >> 16) & 0xFFF0))[0]
        shift = (hdr >> 16) & 0x0F
        out += [hist2, hist1]
        for row in range(15):
            byte = fr[16 + row * 4 + g]
            for nib in (byte >> 4, byte & 0x0F):
                s = ((nib << 12) & 0xFFFF)
                s = (s - 0x10000 if s & 0x8000 else s) >> shift
                s = _clamp16(s + hist1 * c1 + hist2 * c2)
                out.append(s)
                hist2, hist1 = hist1, s
    return out


def decode_xas(blk_iter, channels):
    import array
    chans = [array.array('h') for _ in range(channels)]
    for flag, n, p in blk_iter:
        frames = (n + 127) // 128
        got = 0
        for f in range(frames):
            take = min(128, n - got)
            for c in range(channels):
                o = (f * channels + c) * 0x4C
                chans[c].extend(decode_xas_frame(p[o:o + 0x4C])[:take])
            got += take
    n = min(len(c) for c in chans)
    out = array.array('h', bytes(2 * n * channels))
    for c in range(channels):
        out[c::channels] = chans[c][:n]
    return out
