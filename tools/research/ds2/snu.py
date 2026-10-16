"""Streamed audio (audiostreams/*.exa.snu): 360 EA-XMA -> PC EA-XAS.

SNU container: u8 3, u8 0, u16 (1/2), u32 (platform byte order), u32 offset
of the audio blocks (0x20), u32 0, big-endian EAAudioCore header at 0x10,
then the blocks. Same file name on PC (the exe builds
audiostreams\\%s with .exa)."""
import struct
from . import eaaudio as A


def convert(x, ffmpeg=None):
    if len(x) < 0x20 or x[0] != 3:
        return None
    unk, data = struct.unpack_from('>II', x, 4)
    h = A.parse_header(x, 0x10)
    if h['codec'] != A.CODEC_EAXMA:
        return None
    pcm = A.decode_eaxma(A.blocks(x, data), h['channels'], h['rate'], h['samples'], ffmpeg)
    loop_start = h.get('loop_start') if h['loop'] else None
    body = A.xas_blocks(pcm, h['channels'])
    loop_offset = None
    if loop_start is not None:
        # offset (from the first block) of the block holding the loop start
        per = 27 * 128
        loop_offset = (loop_start // per) * (8 + 27 * 0x4C * h['channels'])
    hdr = A.make_header(A.CODEC_XAS1, h['channels'], h['rate'], h['samples'], type_=h['type'],
                        loop_start=loop_start, loop_offset=loop_offset, version=h['version'])
    start = 0x10 + len(hdr)
    start = (start + 3) // 4 * 4 if start > 0x20 else 0x20
    # 21 of Severed's 237 streams carry an extra block between the header
    # and the audio (u32 at 0x0C = its offset; PC streams have the same
    # kind of block, different content). Not decoded yet: dropped, giving
    # the plain PC layout (0x0C = 0).
    out = bytearray(x[0:4]) + struct.pack('<III', unk, start, 0)
    out += hdr
    out += bytes(start - len(out))
    return bytes(out) + body


LANGS = {'de', 'es', 'fr', 'it'}


def pc_path(rel):
    """archive path of an audio stream on PC. The 360 keeps them flat
    (audiostreams\\[lang\\]<name>.exa.snu); the PC engine looks for
    audiostreams\\[lang\\]<name[4:12]>\\<name>.exa.snu, except for names of 8
    characters or fewer (checked against all 2,045 base-game stream names in
    the PC archives)."""
    parts = rel.replace('/', '\\').split('\\')
    if parts[0].lower() != 'audiostreams' or not parts[-1].lower().endswith('.exa.snu'):
        return rel
    name = parts[-1][:-len('.exa.snu')]
    if len(name) <= 8:
        return '\\'.join(parts)
    return '\\'.join(parts[:-1] + [name[4:12], parts[-1]])
