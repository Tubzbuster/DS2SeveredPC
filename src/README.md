# Severed tools (C#)

- `Severed.Core` (netstandard2.0): format code shared by everything: LZX
  (Xbox XMemCompress) and RefPack decoders, stream file reader, endian and
  name-hash helpers. Will also hold the 360 -> PC converters.
- `Severed.Cli` (net8.0): command-line tool used for development and
  testing (`severed expand in.str out.str`, `severed list in.str`).

Build: `dotnet build src/Severed.Cli -c Release`.

The decoders are checked against the Python research code
(`tools/research`): identical payloads for every asset of the sample
streams, and all 78,498 assets of the 360 export decode without error to
the sizes their headers give.
