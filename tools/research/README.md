# Research code (Python 3)

Prototype readers used to work out the formats. Run from this folder.

- `ds2/lzx.py`: LZX decoder for Xbox 360 XMemCompress data (`LZXD` chunks).
  Verified: 14/14 Lua scripts decode identically to their PC RefPack
  versions.
- `ds2/refpack.py`: EA RefPack decoder (PC `Rpak` chunks).
- `ds2/streamfile.py`: `.str` reader for both platforms (`ols3` / `3slo`):
  assets, headers, decompressed payloads.
- `compare.py PC.str 360.str ...`: per asset type, how many payloads are
  identical / same size / different between platforms.
- `swapcheck.py PC.str 360.str ...`: for same-size pairs, how much matches
  after 32-bit or 16-bit byte swapping.

Python is too slow for the installer (about 1 MB/s for LZX); the installer
will reimplement these.
