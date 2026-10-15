/* EA-XAS v1 encoder: 128 mono samples -> one 0x4C-byte frame.
 * Mirrors the decoder: 4 groups of 32 samples; each group header (u32 LE)
 * carries the first two samples (top 12 bits), the coefficient index and
 * the shift; then 30 4-bit residuals, stored 15 rows x 4 bytes (byte
 * [row*4 + group], high nibble first). For each group every coefficient
 * pair and shift is tried in closed loop, keeping the least squared error. */
#include <stdint.h>
#include <string.h>

static const double coefs[4][2] = {
    {0.0, 0.0}, {0.9375, 0.0}, {1.796875, -0.8125}, {1.53125, -0.859375}
};

static int clamp16(double v)
{
    int s = (int)v;               /* C conversion: truncate toward zero */
    return s < -32768 ? -32768 : s > 32767 ? 32767 : s;
}

/* encodes 32 samples; returns header, writes 30 nibbles */
static uint32_t enc_group(const int16_t *x, uint8_t *nib)
{
    int16_t h2 = (int16_t)(x[0] & 0xFFF0), h1 = (int16_t)(x[1] & 0xFFF0);
    double best = 1e300;
    uint32_t best_hdr = 0;
    uint8_t cur[30];
    for (int c = 0; c < 4; c++) {
        for (int shift = 0; shift <= 12; shift++) {
            double err = 0;
            int hist1 = h1, hist2 = h2;
            int step = 1 << (12 - shift);
            for (int i = 0; i < 30; i++) {
                double pred = hist1 * coefs[c][0] + hist2 * coefs[c][1];
                double d = (x[i + 2] - pred) / step;
                int n = (int)(d < 0 ? d - 0.5 : d + 0.5);
                if (n < -8) n = -8;
                if (n > 7) n = 7;
                /* decoder: (int16)(nib << 12) >> shift, then + pred */
                int16_t v = (int16_t)(n << 12);
                int s = clamp16((v >> shift) + pred);
                double e = (double)(s - x[i + 2]);
                err += e * e;
                if (err >= best) break;
                cur[i] = (uint8_t)(n & 0x0F);
                hist2 = hist1;
                hist1 = s;
            }
            if (err < best) {
                best = err;
                memcpy(nib, cur, 30);
                best_hdr = ((uint32_t)(uint16_t)h2 & 0xFFF0) | (uint32_t)c |
                           (((uint32_t)(uint16_t)h1 & 0xFFF0) << 16) | ((uint32_t)shift << 16);
            }
        }
    }
    return best_hdr;
}

/* frame: 0x4C bytes out; x: 128 samples (pad with zeros if fewer) */
void xas_encode_frame(const int16_t *x, uint8_t *frame)
{
    uint8_t nib[4][30];
    memset(frame, 0, 0x4C);
    for (int g = 0; g < 4; g++) {
        uint32_t h = enc_group(x + 32 * g, nib[g]);
        frame[4 * g + 0] = h & 0xFF;
        frame[4 * g + 1] = (h >> 8) & 0xFF;
        frame[4 * g + 2] = (h >> 16) & 0xFF;
        frame[4 * g + 3] = (h >> 24) & 0xFF;
    }
    for (int row = 0; row < 15; row++)
        for (int g = 0; g < 4; g++)
            frame[16 + row * 4 + g] = (uint8_t)((nib[g][2 * row] << 4) | nib[g][2 * row + 1]);
}

/* many frames: n_frames * 128 samples of one channel (contiguous) */
void xas_encode(const int16_t *x, int n_frames, uint8_t *out)
{
    for (int f = 0; f < n_frames; f++)
        xas_encode_frame(x + 128 * f, out + 0x4C * f);
}
