using System;
using System.IO;

namespace Severed
{
    /// <summary>
    /// LZX decoder for Xbox 360 XMemCompress "native" data (the LZXD chunks of
    /// .str files). Algorithm as in libmspack's lzxd.c; framing: each frame is
    /// [FF uu uu cc cc] or [cc cc] (big-endian u16 sizes) then cc compressed
    /// bytes producing uu (default 0x8000) bytes. Decoder state carries across
    /// frames; the bit reader restarts at each frame.
    /// </summary>
    public sealed class LzxDecoder
    {
        const int MinMatch = 2, NumChars = 256, PretreeNum = 20, AlignedNum = 8, LengthNum = 249;
        public const int FrameSize = 0x8000;

        static readonly int[] Extra = new int[52];
        static readonly int[] Base = new int[52];
        static LzxDecoder()
        {
            int j = 0;
            for (int i = 0; i < 52; i += 2) { Extra[i] = j; Extra[i + 1] = j; if (i != 0 && j < 17) j++; }
            Base[0] = 0;
            for (int i = 0; i < 51; i++) Base[i + 1] = Base[i] + (1 << Extra[i]);
        }

        sealed class Huff
        {
            public int Max;
            public ushort[] Sym;   // index by top Max bits
            public byte[] Len;
            public Huff(byte[] lens, int n)
            {
                Max = 0;
                for (int i = 0; i < n; i++) if (lens[i] > Max) Max = lens[i];
                if (Max == 0) return;
                int size = 1 << Max;
                Sym = new ushort[size];
                Len = new byte[size];
                int code = 0;
                for (int bits = 1; bits <= Max; bits++)
                {
                    for (int s = 0; s < n; s++)
                    {
                        if (lens[s] != bits) continue;
                        int start = code << (Max - bits), end = start + (1 << (Max - bits));
                        if (end > size) throw new InvalidDataException("LZX: over-subscribed Huffman table");
                        for (int k = start; k < end; k++) { Sym[k] = (ushort)s; Len[k] = (byte)bits; }
                        code++;
                    }
                    code <<= 1;
                }
            }
        }

        // bit reader (libmspack semantics: 16-bit little-endian words, MSB first)
        byte[] _in; int _pos, _end; uint _buf; int _left;
        void Word()
        {
            uint w = _pos + 1 < _end ? (uint)(_in[_pos] | (_in[_pos + 1] << 8)) : 0u;
            _pos += 2;
            _buf |= w << (16 - _left);
            _left += 16;
        }
        void Ensure(int n) { while (_left < n) Word(); }
        int Read(int n)
        {
            if (n == 0) return 0;
            Ensure(n);
            int v = (int)(_buf >> (32 - n));
            _buf <<= n; _left -= n;
            return v;
        }
        int ReadSym(Huff h)
        {
            if (h == null || h.Sym == null) throw new InvalidDataException("LZX: empty Huffman tree used");
            Ensure(16);
            int idx = (int)(_buf >> (32 - h.Max));
            int l = h.Len[idx];
            _buf <<= l; _left -= l;
            return h.Sym[idx];
        }

        readonly int _slots;
        readonly byte[] _mainLens, _lenLens = new byte[LengthNum];
        int _r0 = 1, _r1 = 1, _r2 = 1;
        bool _headerRead;
        int _blockType, _blockRemaining, _blockLength;
        Huff _main, _length, _aligned;
        byte[] _out; int _outLen; long _total;

        public LzxDecoder(int windowBits = 17)
        {
            switch (windowBits)
            {
                case 15: _slots = 30; break; case 16: _slots = 32; break; case 17: _slots = 34; break;
                case 18: _slots = 36; break; case 19: _slots = 38; break; case 20: _slots = 42; break;
                case 21: _slots = 50; break;
                default: throw new ArgumentException("bad window size");
            }
            _mainLens = new byte[NumChars + _slots * 8];
        }

        void ReadLens(byte[] lens, int first, int last)
        {
            var pre = new byte[PretreeNum];
            for (int i = 0; i < PretreeNum; i++) pre[i] = (byte)Read(4);
            var pt = new Huff(pre, PretreeNum);
            int x = first;
            while (x < last)
            {
                int z = ReadSym(pt);
                if (z == 17) { int n = Read(4) + 4; for (int k = 0; k < n && x < lens.Length; k++) lens[x++] = 0; }
                else if (z == 18) { int n = Read(5) + 20; for (int k = 0; k < n && x < lens.Length; k++) lens[x++] = 0; }
                else if (z == 19)
                {
                    int n = Read(1) + 4;
                    z = ReadSym(pt);
                    int v = ((lens[x] - z) % 17 + 17) % 17;
                    for (int k = 0; k < n && x < lens.Length; k++) lens[x++] = (byte)v;
                }
                else { lens[x] = (byte)(((lens[x] - z) % 17 + 17) % 17); x++; }
            }
        }

        void Put(byte b)
        {
            if (_outLen == _out.Length) Array.Resize(ref _out, _out.Length * 2);
            _out[_outLen++] = b;
        }

        void DecodeFrame(byte[] data, int pos, int end, int frameOut)
        {
            _in = data; _pos = pos; _end = end; _buf = 0; _left = 0;
            long target = _total + frameOut;
            _total = target;
            if (!_headerRead)
            {
                if (Read(1) != 0)
                {
                    int hi = Read(16), lo = Read(16);
                    if (((hi << 16) | lo) != 0) throw new NotSupportedException("LZX: Intel E8 translation not implemented");
                }
                _headerRead = true;
            }
            while (_outLen < target)
            {
                if (_blockRemaining == 0)
                {
                    if (_blockType == 3 && (_blockLength & 1) != 0) _pos++;
                    _blockType = Read(3);
                    _blockLength = _blockRemaining = (Read(16) << 8) | Read(8);
                    if (_blockType == 2)
                    {
                        var al = new byte[AlignedNum];
                        for (int i = 0; i < AlignedNum; i++) al[i] = (byte)Read(3);
                        _aligned = new Huff(al, AlignedNum);
                    }
                    if (_blockType == 1 || _blockType == 2)
                    {
                        ReadLens(_mainLens, 0, NumChars);
                        ReadLens(_mainLens, NumChars, NumChars + _slots * 8);
                        _main = new Huff(_mainLens, _mainLens.Length);
                        ReadLens(_lenLens, 0, LengthNum);
                        _length = new Huff(_lenLens, LengthNum);
                    }
                    else if (_blockType == 3)
                    {
                        if (_left == 0) Ensure(16);
                        _buf = 0; _left = 0;
                        _r0 = BitConverter.ToInt32(data, _pos); _r1 = BitConverter.ToInt32(data, _pos + 4); _r2 = BitConverter.ToInt32(data, _pos + 8);
                        _pos += 12;
                    }
                    else throw new InvalidDataException("LZX: bad block type " + _blockType);
                }

                int run = (int)Math.Min(_blockRemaining, target - _outLen);
                if (_blockType == 3)
                {
                    for (int k = 0; k < run; k++) Put(data[_pos + k]);
                    _pos += run;
                    _blockRemaining -= run;
                    continue;
                }
                bool aligned = _blockType == 2;
                int produced = 0;
                while (produced < run)
                {
                    int e = ReadSym(_main);
                    if (e < NumChars) { Put((byte)e); produced++; continue; }
                    e -= NumChars;
                    int ml = e & 7;
                    if (ml == 7) ml += ReadSym(_length);
                    ml += MinMatch;
                    int slot = e >> 3, off;
                    if (slot == 0) off = _r0;
                    else if (slot == 1) { off = _r1; _r1 = _r0; _r0 = off; }
                    else if (slot == 2) { off = _r2; _r2 = _r0; _r0 = off; }
                    else
                    {
                        int extra = slot >= 36 ? 17 : Extra[slot];
                        off = Base[slot] - 2;
                        if (!aligned)
                        {
                            if (slot == 3) off = 1; else off += Read(extra);
                        }
                        else if (extra > 3) { off += Read(extra - 3) << 3; off += ReadSym(_aligned); }
                        else if (extra == 3) off += ReadSym(_aligned);
                        else if (extra > 0) off += Read(extra);
                        else off = 1;
                        _r2 = _r1; _r1 = _r0; _r0 = off;
                    }
                    if (off > _outLen) throw new InvalidDataException("LZX: match offset before start of data");
                    int src = _outLen - off;
                    for (int k = 0; k < ml; k++) Put(_out[src + k]);
                    produced += ml;
                }
                _blockRemaining -= produced;
                if (_blockRemaining < 0) throw new InvalidDataException("LZX: match ran past end of block");
            }
        }

        /// <summary>Decompress XMemCompress native frames data[offset..offset+length), at most usize bytes.</summary>
        public static byte[] XmemDecompress(byte[] data, int offset, int length, int usize, int windowBits = 17)
        {
            var d = new LzxDecoder(windowBits) { _out = new byte[Math.Max(usize + 512, 1024)] };
            int pos = offset, end = offset + length, produced = 0;
            while (produced < usize && pos < end)
            {
                int fu, fc;
                if (data[pos] == 0xFF)
                {
                    fu = (data[pos + 1] << 8) | data[pos + 2];
                    fc = (data[pos + 3] << 8) | data[pos + 4];
                    pos += 5;
                }
                else { fu = FrameSize; fc = (data[pos] << 8) | data[pos + 1]; pos += 2; }
                if (fc == 0) break;
                fu = Math.Min(fu, usize - produced);
                d.DecodeFrame(data, pos, pos + fc, fu);
                produced += fu;
                pos += fc;
            }
            // An asset split over several LZXD chunks has each chunk compressed on its
            // own; a chunk yields only the frames it contains.
            var result = new byte[Math.Min(produced, d._outLen)];
            Buffer.BlockCopy(d._out, 0, result, 0, result.Length);
            return result;
        }
    }
}
