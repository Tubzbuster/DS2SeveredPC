/* EA RefPack (QFS) decompressor for the PC .str 'Rpak' chunks; same
   algorithm as ds2/refpack.py, for speed. Returns the number of bytes
   written, or -1 on bad data. */
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

EXPORT long refpack_decompress(const uint8_t *src, long srclen, uint8_t *dst, long dstlen)
{
    long i, o = 0, n, usize, k;
    uint8_t flags;
    if (srclen < 5 || src[1] != 0xFB) return -1;
    flags = src[0];
    i = 2;
    n = (flags & 0x80) ? 4 : 3;
    if (flags & 0x01) i += n;
    usize = 0;
    for (k = 0; k < n; k++) usize = (usize << 8) | src[i + k];
    i += n;
    if (usize > dstlen) return -1;
    for (;;) {
        long lit, length = 0, off = 0;
        uint8_t b0;
        if (i >= srclen) return -1;
        b0 = src[i++];
        if (b0 < 0x80) {
            if (i + 1 > srclen) return -1;
            lit = b0 & 3; length = ((b0 & 0x1C) >> 2) + 3; off = ((b0 & 0x60) << 3) + src[i] + 1; i += 1;
        } else if (b0 < 0xC0) {
            if (i + 2 > srclen) return -1;
            lit = src[i] >> 6; length = (b0 & 0x3F) + 4; off = ((src[i] & 0x3F) << 8) + src[i + 1] + 1; i += 2;
        } else if (b0 < 0xE0) {
            if (i + 3 > srclen) return -1;
            lit = b0 & 3; length = ((b0 & 0x0C) << 6) + src[i + 2] + 5;
            off = ((long)(b0 & 0x10) << 12) + (src[i] << 8) + src[i + 1] + 1; i += 3;
        } else if (b0 < 0xFC) {
            lit = ((b0 & 0x1F) << 2) + 4;
            if (i + lit > srclen || o + lit > usize) return -1;
            for (k = 0; k < lit; k++) dst[o++] = src[i++];
            continue;
        } else {
            lit = b0 & 3;
            if (i + lit > srclen || o + lit > usize) return -1;
            for (k = 0; k < lit; k++) dst[o++] = src[i++];
            break;
        }
        if (i + lit > srclen || o + lit + length > usize) return -1;
        for (k = 0; k < lit; k++) dst[o++] = src[i++];
        if (off > o) return -1;
        for (k = 0; k < length; k++, o++) dst[o] = dst[o - off];
    }
    return o == usize ? o : -1;
}
