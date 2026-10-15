using System;
using System.IO;

namespace Severed
{
    /// <summary>EA RefPack (QFS) decompression, as used by PC .str 'Rpak' chunks.</summary>
    public static class RefPack
    {
        public static byte[] Decompress(byte[] src, int pos)
        {
            int flags = src[pos];
            if (src[pos + 1] != 0xFB) throw new InvalidDataException("not RefPack (no 0xFB marker)");
            int i = pos + 2;
            int n = (flags & 0x80) != 0 ? 4 : 3;
            if ((flags & 0x01) != 0) i += n;
            int usize = 0;
            for (int k = 0; k < n; k++) usize = (usize << 8) | src[i + k];
            i += n;
            var o = new byte[usize];
            int op = 0;
            while (true)
            {
                int b0 = src[i++], lit, len = 0, off = 0;
                if (b0 < 0x80)
                {
                    int b1 = src[i++];
                    lit = b0 & 3; len = ((b0 & 0x1C) >> 2) + 3; off = ((b0 & 0x60) << 3) + b1 + 1;
                }
                else if (b0 < 0xC0)
                {
                    int b1 = src[i++], b2 = src[i++];
                    lit = b1 >> 6; len = (b0 & 0x3F) + 4; off = ((b1 & 0x3F) << 8) + b2 + 1;
                }
                else if (b0 < 0xE0)
                {
                    int b1 = src[i++], b2 = src[i++], b3 = src[i++];
                    lit = b0 & 3; len = ((b0 & 0x0C) << 6) + b3 + 5; off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1;
                }
                else if (b0 < 0xFC)
                {
                    lit = ((b0 & 0x1F) << 2) + 4;
                    Buffer.BlockCopy(src, i, o, op, lit); i += lit; op += lit;
                    continue;
                }
                else
                {
                    lit = b0 & 3;
                    Buffer.BlockCopy(src, i, o, op, lit); i += lit; op += lit;
                    break;
                }
                Buffer.BlockCopy(src, i, o, op, lit); i += lit; op += lit;
                int s = op - off;
                if (s < 0) throw new InvalidDataException("RefPack offset before start");
                for (int k = 0; k < len; k++) o[op++] = o[s + k];
            }
            if (op != usize) throw new InvalidDataException("RefPack size mismatch");
            return o;
        }
    }
}
