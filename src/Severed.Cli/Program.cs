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
