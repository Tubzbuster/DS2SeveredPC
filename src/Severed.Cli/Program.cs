using System;
using System.IO;
using System.Linq;
using System.Text;

namespace Severed.Cli
{
    static class Program
    {
        static int Main(string[] args)
        {
            Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
            if (args.Length == 0) { Console.Error.WriteLine("usage: severed <command> ..."); return 1; }
            switch (args[0])
            {
                case "expand":   // expand <in.str> <out.str>
                {
                    var sw = System.Diagnostics.Stopwatch.StartNew();
                    var d = File.ReadAllBytes(args[1]);
                    using (var f = File.Create(args[2])) StreamFile.Expand(d, f);
                    Console.WriteLine($"{args[1]}: {d.Length:N0} -> {new FileInfo(args[2]).Length:N0} bytes in {sw.Elapsed.TotalSeconds:F1}s");
                    return 0;
                }
                case "split":    // split <in.str> <outdir>: one stream file per asset type
                {
                    Directory.CreateDirectory(args[2]);
                    var outs = new System.Collections.Generic.Dictionary<string, FileStream>();
                    var d = new byte[12];
                    using (var input = new BufferedStream(File.OpenRead(args[1]), 1 << 20))
                    try
                    {
                        foreach (var a in StreamFile.ReadAll(input, d))
                        {
                            if (!outs.TryGetValue(a.Type, out var f))
                            {
                                f = File.Create(Path.Combine(args[2], a.Type + ".str"));
                                f.Write(d, 0, 12);
                                outs[a.Type] = f;
                            }
                            f.Write(a.Header, 0, a.Header.Length);
                            foreach (var c in a.Chunks) f.Write(c.Data, 0, c.Data.Length);
                        }
                    }
                    finally { foreach (var f in outs.Values) f.Dispose(); }
                    Console.WriteLine($"{args[1]}: {outs.Count} types -> {args[2]}");
                    return 0;
                }
                case "list":     // list <in.str>
                {
                    foreach (var a in StreamFile.Read(File.ReadAllBytes(args[1])))
                        Console.WriteLine($"{a.Type}\t{a.Name}\t{a.Size}\t{string.Join("+", a.Chunks.Select(c => c.Kind))}");
                    return 0;
                }
                default:
                    Console.Error.WriteLine("unknown command " + args[0]);
                    return 1;
            }
        }
    }
}
