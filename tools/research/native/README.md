# Native helpers: EA-XAS encoder and RefPack decompressor

Two small C libraries, built into one `xasenc.dll` (64-bit Windows) or
`libxasenc.so` (Linux). They have no dependencies and nothing specific to
Dead Space 2, so other EA-format projects can use them as they are, under the
repository's zlib licence (`LICENSE` at the top of the repo).

## `xas_enc.c`: EA-XAS v1 encoder

EA-XAS is the 4-bit ADPCM codec in EA's EAAudioCore streams (`.snu`, `.snr`,
`.sns`, sound bank samples): codec 4, used by many EA PC games of the late
2000s and early 2010s. vgmstream and FFmpeg can decode it. The usual
encoder is EA's own `sx.exe`; we found no open-source encoder, which is why
this one was written.

```c
void xas_encode(const int16_t *x, int n_frames, uint8_t *out);
```

- **In:** one channel of 16-bit PCM, `n_frames * 128` samples. Pad the last
  frame with silence.
- **Out:** `n_frames * 0x4C` bytes, one 76-byte frame per 128 samples.
- **Several channels:** encode each channel separately, then interleave the
  frames per channel in each block (`ds2/eaaudio.py` `xas_blocks` does this
  and writes the EAAudioCore block headers).
- **Method:** each 32-sample group is tried with all 4 coefficient pairs and
  all 13 shifts in closed loop (the encoder runs the decoder's own
  prediction), keeping the one with the least squared error. The frame
  layout is the one vgmstream's decoder reads (no vgmstream code used).
- **Quality:** the Dead Space 2 PC game plays the output.
  Severed's audio converted EA-XMA -> PCM -> XAS measured 26-60 dB SNR
  against the decoded source.

## `refpack.c`: RefPack (QFS) decompressor

EA's LZ77-style RefPack compression, as found in the `Rpak` chunks of
Dead Space 2 PC `.str` streams, for speed. The same algorithm is in
`ds2/refpack.py`.

```c
long refpack_decompress(const uint8_t *src, long srclen, uint8_t *dst, long dstlen);
```

It returns the number of bytes written, or -1 on bad or truncated data. It
never writes past `dstlen`.

## Building

`build.sh` builds both: gcc for the Linux library, and Zig's C compiler
(`pip install ziglang==0.13.0`) for the Windows DLL.

## Python use

```python
import ctypes
lib = ctypes.CDLL('xasenc.dll')
lib.xas_encode(pcm_ptr, n_frames, out_buf)    # see ds2/eaaudio.py
```
