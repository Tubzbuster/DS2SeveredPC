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

## Helper scripts (analysis and checks)

Kept from the research sessions so a new session does not have to recreate
them. They read game files from the user's own copies and print results;
they contain no game data.

- **`re/`: static analysis of the retail exe** (capstone,
  `pip install capstone`). Set `DS2_EXE` to the user's unwrapped
  `deadspace2.exe`; it is for analysis only, never run or committed. Run
  from `re/`:
  - `dsx.py`: `dis(addr, n)` disassembles with string annotations;
    `func_start(addr)`, `cstr(addr)`, `v2f`/`f2v` convert addresses and file
    offsets, and `TX`/`TX0` give the .text bytes and base.
  - `hkc.py` / `mem.py` / `hkschema.py`: find the Havok class
    registrations and member tables (the source of `ds2/hkx_classes.json`).

  Example:
  `cd re; DS2_EXE=/path/deadspace2.exe python3 -c "from dsx import *; print('\n'.join(dis(0x5BADE0, 20)))"`
- **`simgroup_tools/`: SimGroup inspection** (360 data):
  - `sgdump.py`: object records (index, handle, class, strings);
  - `sgobj.py <dir> <handle or text>...`: an object's fields by class
    layout;
  - `sgguid.py <dir> <GUID>...`: which object a GUID is;
  - `sghdr.py`: header conversion checks against the pairs;
  - `sgverify.py <pickle>`: converts every SimGroup and re-parses the
    output.
- **`checks/`: consistency checks of converted data:**
  - `rangecheck.py <str>...`: mesh index ranges;
  - `volcheck.py <str>...`: MeshVolatile stream slots;
  - `stripval.py`, `gridval.py`: triangle strips and per-table grids
    against the pairs;
  - `hkxsane.py <dir>`: storage-mesh HKX conversions;
  - `meshdump.py <str> [n]`: mesh header and tables;
  - `rcbexp.py RCB|BNK`: compares the relocation-model options held-out.
- **`rpenc.py`:** a simple RefPack encoder (`enc(data)`), to make test
  chunks for the native decoder.
- **`native/test_harness.c`:** an AddressSanitizer/valgrind harness for
  `refpack.c` and `xas_enc.c`. It decodes real chunks (records of
  `u32 len, u32 size, compressed, expected`), fuzzes truncated or flipped
  input, and encodes random audio. Build it with
  `gcc -g -fsanitize=address,undefined test_harness.c refpack.c xas_enc.c`.

