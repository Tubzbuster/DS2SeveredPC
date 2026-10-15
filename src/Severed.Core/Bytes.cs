using System;

namespace Severed
{
    /// <summary>Endian helpers.</summary>
    public static class Bytes
    {
        public static uint U32(byte[] b, int o, bool be) =>
            be ? (uint)(b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]) : BitConverter.ToUInt32(b, o);
        public static ushort U16(byte[] b, int o, bool be) =>
            be ? (ushort)(b[o] << 8 | b[o + 1]) : BitConverter.ToUInt16(b, o);
        public static void PutU32(byte[] b, int o, uint v, bool be)
        {
            if (be) { b[o] = (byte)(v >> 24); b[o + 1] = (byte)(v >> 16); b[o + 2] = (byte)(v >> 8); b[o + 3] = (byte)v; }
            else { b[o] = (byte)v; b[o + 1] = (byte)(v >> 8); b[o + 2] = (byte)(v >> 16); b[o + 3] = (byte)(v >> 24); }
        }
        public static void PutU16(byte[] b, int o, ushort v, bool be)
        {
            if (be) { b[o] = (byte)(v >> 8); b[o + 1] = (byte)v; } else { b[o] = (byte)v; b[o + 1] = (byte)(v >> 8); }
        }
        public static void Swap32(byte[] b, int o, int count)
        {
            for (int i = o; i + 3 < o + count; i += 4)
            {
                byte t = b[i]; b[i] = b[i + 3]; b[i + 3] = t;
                t = b[i + 1]; b[i + 1] = b[i + 2]; b[i + 2] = t;
            }
        }
        public static void Swap16(byte[] b, int o, int count)
        {
            for (int i = o; i + 1 < o + count; i += 2) { byte t = b[i]; b[i] = b[i + 1]; b[i + 1] = t; }
        }
        /// <summary>sdbm hash of the lowercase path: the BIGH archive name hash.</summary>
        public static uint NameHash(string path)
        {
            uint h = 0;
            foreach (char c in path.ToLowerInvariant()) h = h * 65599u + (byte)c;
            return h;
        }
    }
}
