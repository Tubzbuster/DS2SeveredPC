using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Severed
{
    /// <summary>One data chunk of an asset, as stored.</summary>
    public sealed class StreamChunk
    {
        public string Kind;     // SDAT, LZXD, Rpak
        public byte[] Data;     // the whole chunk including its 12-byte header
    }

    /// <summary>An asset in a stream file: its SHDR header chunk and its data chunks.</summary>
    public sealed class StreamAsset
    {
        public bool BigEndian;
        public byte[] Header;   // the whole SHDR chunk
        public List<StreamChunk> Chunks = new List<StreamChunk>();

        public uint TypeHash => Bytes.U32(Header, 12, BigEndian);
        public ushort Flags0 => Bytes.U16(Header, 16, BigEndian);
        public ushort Flags1 => Bytes.U16(Header, 18, BigEndian);
        public uint Id(int i) => Bytes.U32(Header, 20 + 4 * i, BigEndian);
        public int Size => (int)Bytes.U32(Header, 40, BigEndian);
        public string Name => Str(0);
        public string SourcePath => Str(1);
        public string Type => Str(2);
        public string Key => Type + "|" + Name.ToLowerInvariant() + "|" + Id(0).ToString("X8") + Id(1).ToString("X8") + Id(2).ToString("X8") + Id(3).ToString("X8") + Id(4).ToString("X8");

        string Str(int index)
        {
            int o = 44;
            for (int k = 0; k < index; k++) { while (o < Header.Length && Header[o] != 0) o++; o++; }
            int s = o;
            while (o < Header.Length && Header[o] != 0) o++;
            return s < Header.Length ? Encoding.GetEncoding(28591).GetString(Header, s, o - s) : "";
        }

        /// <summary>Decompressed payload.</summary>
        public byte[] Payload()
        {
            var o = new MemoryStream(Size);
            foreach (var c in Chunks)
            {
                int left = Size - (int)o.Length;
                if (c.Kind == "SDAT") o.Write(c.Data, 12, Math.Min(c.Data.Length - 12, left));
                else if (c.Kind == "LZXD")
                {
                    int csize = (int)Bytes.U32(c.Data, 12, true);
                    var d = LzxDecoder.XmemDecompress(c.Data, 16, csize, left);
                    o.Write(d, 0, d.Length);
                }
                else if (c.Kind == "Rpak") { var d = RefPack.Decompress(c.Data, 16); o.Write(d, 0, d.Length); }
                else throw new InvalidDataException("unknown data chunk " + c.Kind);
            }
            return o.ToArray();
        }
    }

    /// <summary>Reader for .str stream files: 'ols3' (360, big-endian) and '3slo' (PC).</summary>
    public static class StreamFile
    {
        public static string Tag(byte[] d, int o, bool be) =>
            be ? Encoding.ASCII.GetString(d, o, 4) : new string(new[] { (char)d[o + 3], (char)d[o + 2], (char)d[o + 1], (char)d[o] });

        public static bool IsStream(byte[] d, out bool be)
        {
            be = d.Length >= 4 && d[0] == 'o' && d[1] == 'l' && d[2] == 's' && d[3] == '3';
            return be || (d.Length >= 4 && d[0] == '3' && d[1] == 's' && d[2] == 'l' && d[3] == 'o');
        }

        public static List<StreamAsset> Read(byte[] d)
        {
            if (!IsStream(d, out bool be)) throw new InvalidDataException("not a stream file");
            var list = new List<StreamAsset>();
            StreamAsset cur = null;
            int o = 12;
            while (o + 12 <= d.Length)
            {
                int size = (int)Bytes.U32(d, o + 4, be);
                if (size < 8 || o + size > d.Length) break;
                if (Tag(d, o, be) == "SHOC")
                {
                    string sub = Tag(d, o + 8, be);
                    var c = new byte[size];
                    Buffer.BlockCopy(d, o, c, 0, size);
                    if (sub == "SHDR") { cur = new StreamAsset { BigEndian = be, Header = c }; list.Add(cur); }
                    else if (cur != null) cur.Chunks.Add(new StreamChunk { Kind = sub, Data = c });
                }
                o += size;
            }
            return list;
        }

        /// <summary>Reads assets one at a time from a stream file of any size.</summary>
        public static IEnumerable<StreamAsset> ReadAll(Stream f, byte[] fileHeader = null)
        {
            var h = new byte[12];
            if (f.Read(h, 0, 12) != 12 || !IsStream(h, out bool be)) throw new InvalidDataException("not a stream file");
            if (fileHeader != null) Buffer.BlockCopy(h, 0, fileHeader, 0, 12);
            StreamAsset cur = null;
            var ch = new byte[12];
            while (true)
            {
                int got = 0;
                while (got < 12) { int r = f.Read(ch, got, 12 - got); if (r <= 0) break; got += r; }
                if (got < 12) break;
                int size = (int)Bytes.U32(ch, 4, be);
                if (size < 12) break;
                var c = new byte[size];
                Buffer.BlockCopy(ch, 0, c, 0, 12);
                got = 12;
                while (got < size) { int r = f.Read(c, got, size - got); if (r <= 0) throw new EndOfStreamException(); got += r; }
                if (Tag(c, 0, be) != "SHOC") continue;
                string sub = Tag(c, 8, be);
                if (sub == "SHDR")
                {
                    if (cur != null) yield return cur;
                    cur = new StreamAsset { BigEndian = be, Header = c };
                }
                else if (cur != null) cur.Chunks.Add(new StreamChunk { Kind = sub, Data = c });
            }
            if (cur != null) yield return cur;
        }

        /// <summary>Copy of a stream file with every compressed chunk replaced by one SDAT chunk (same endianness).</summary>
        public static byte[] Expand(byte[] d)
        {
            var o = new MemoryStream();
            Expand(d, o);
            return o.ToArray();
        }

        /// <summary>As <see cref="Expand(byte[])"/>, writing to a stream.</summary>
        public static void Expand(byte[] d, Stream o)
        {
            IsStream(d, out bool be);
            o.Write(d, 0, 12);
            foreach (var a in Read(d))
            {
                o.Write(a.Header, 0, a.Header.Length);
                var p = a.Payload();
                int pad = (4 - p.Length % 4) % 4;
                var h = new byte[12];
                Encoding.ASCII.GetBytes(be ? "SHOC" : "COHS").CopyTo(h, 0);
                Bytes.PutU32(h, 4, (uint)(12 + p.Length + pad), be);
                Encoding.ASCII.GetBytes(be ? "SDAT" : "TADS").CopyTo(h, 8);
                o.Write(h, 0, 12);
                o.Write(p, 0, p.Length);
                o.Write(new byte[pad], 0, pad);
            }
        }
    }
}
