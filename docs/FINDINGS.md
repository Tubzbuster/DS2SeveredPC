# Findings from the first scans

Source: `PC`, `Base360` and `Severed360` scans (first scanner version).
Everything here is read from file headers and string tables. Nothing has
been run or disassembled yet.

## 1. How the Severed DLC is packaged

One Xbox 360 `LIVE` package, title ID `0x454108DF`, "Dead Space™ 2: Severed",
1.43 GB, 421 files in 167 folders. Contents:

| What | Files | Size | Notes |
|------|------:|-----:|-------|
| `pdlc1_ch01_mng/**/*.str` | 164 | 1.32 GB | Level streams for the new chapter, magic `ols3` |
| `audiostreams/**/*.exa.snu` | 237 | 101 MB | Music, ambience and dialogue (+ de/es/fr/it) |
| `movies/<lang>/*.vp6` | 10 | 104 MB | Two video logs, 5 languages |
| `pdlc1_ch01_mng/*.toc` | 2 | 36 KB | Stream tables of contents (big-endian binary) |
| `*.add` | 2 | 13 KB | Text list of every stream in the chapter, plus a 32-bit value each |
| `weller1.*` | 5 | 11 KB | Text descriptors of the DLC (below) |
| `spa.bin` | 1 | 620 KB | Xbox achievements/strings (XDBF). Not needed on PC |

The `weller1.*` files are the DLC's manifest, written by EA's
"BuildDlcPackage tool":

- `weller1.key`: bundle key `PDLC_WELLER1`
- `weller1.pid`: internal package name `weller1`, package version 2
- `weller1.lvl`: the playable level. Name/description string IDs
  (`$weller1_map_name` …), map folder `pdlc1_ch01_mng`, stream
  `pdlc1_ch01_mng.str`, checkpoint GUID, save-chapter name, unlock key 0
  ("always unlocked")
- `weller1.lds`: a stream loaded **in the front end** (load mask 1):
  `pdlc1_ch01_mng\pdlc1_ch01_mng\dlc_support\level_select.str`. This is
  most likely what adds the Severed entry to the main menu on console.
  The menu option ships *with the DLC*, not in the game exe.
- `weller1.dlm`: list of the DLC's audio streams and their folders

The new chapter reuses Titan Station areas (hospital, psych ward, mining
camp, …) and pulls shared assets from the base game by path.

## 2. The base game on both platforms uses the same archive format

| | PC (Steam, app 47780) | Xbox 360 (2 discs) |
|-|----|----|
| Archives | `DS2DAT0,1,6,7,8,9.DAT` (8.5 GB) | `bigfile0/1.viv` per disc (12.5 GB) |
| Magic | `BIGH` | `BIGH` |

Layout (same on both): `BIGH`, u32 little-endian archive size, u32
big-endian entry count, u32 big-endian header size, then 12-byte
big-endian entries `{offset, size, name hash}` sorted by hash.

The **name hashes match across platforms**. For example, hash `0x002303E6`
is in PC `DS2DAT0.DAT` (1,762,512 bytes) and 360 `bigfile0.viv`
(1,815,513 bytes). That means every PC file can be paired with its 360
counterpart. Those pairs are what the 360 → PC converter will be built
and tested against.

`DS2DAT2`–`5` are missing on PC. Those slots could be where an extra
archive (ours) gets picked up; still to be checked.

## 3. Asset formats

| Asset | Severed (360) | PC | Expected work |
|-------|---------------|----|---------------|
| Video `.vp6` | EA VP6 (`MVhd` + `SCHl` audio), 640×480 | Same format (`movies\*.vp6`) | Probably **copy as-is** |
| Audio `.snu` | EA SNU, codec byte `3` = **EA-XMA** (360-only) | Unknown yet (exe contains a Speex decoder) | Decode XMA, re-encode to the PC codec |
| Level streams `.str` | `ols3` chunked format (`SHOC`/`SHDR`/`SDAT`), big-endian, DXT textures | Inside DAT archives; not seen yet | Compare 360/PC pairs; likely byte swaps + texture untiling |
| `.toc` | Big-endian binary | Not seen yet | Compare pairs |
| Text descriptors | Plain text | n/a | Copy as-is |

## 4. The PC exe still contains the console DLC system

`deadspace2.exe` (32-bit) has, among others:
`pdlcScanConsumables`, `pdlcProcessConsumables`, `pdlcPurchase`,
`pdlcComplete`, `m_enablePDLCScanning`, `$dlc_package_scanning`,
`$pdlc_waiting_for_scan`, `$pdlc_waiting_for_download`, `NewDLCAvailable`,
`mDLCName`/`mDLCDesc`/`mDLCPrice`, `loadChapters`, `CMD_SetPDLCItemGUID`,
`%s\%s.toc`, `%s\%s_streamsets.str`, and Blaze entitlement calls.

So the engine-side DLC code (UI, level loading, entitlement checks) appears
to be compiled into the PC build. What PC most likely lacks is the
*platform* part: the code that finds and mounts DLC packages (on 360 that's
the Xbox content APIs). If so, the mod mostly needs to supply that piece,
not rebuild the menu.

## 5. Protection on the PC exe

- Steam DRM wrapper (`.bind` section)
- Tages **Solidshield** (`activation.exe`, `activation.x86.dll`, randomly
  named sections `ri`, `aYv`, `QuFIo`, `sr`, zeroed link timestamp)

Consequences:
- Never modify `deadspace2.exe` on disk. Only a DLL loaded at runtime.
- Prefer hooks that don't patch game code, e.g. redirecting Windows
  file-API calls (`CreateFile`, `FindFirstFile`) so the game finds our files.
  Integrity checks are less likely to notice that.
- The mod does not remove or bypass the DRM. It still runs and activates
  as normal.

## 6. Revised plan

1. **Next scans** (new scanner): list every entry inside the BIGH archives
   on both platforms, so 360/PC pairs of `.str`, `.snu` and `.toc` can be
   compared, and the PC audio codec identified.
2. **Name hash:** work out the hash function from known names (exe strings
   like `frontend.str`, `global_assets.str`, chapter names from
   `disc1_info.txt`) against the full hash lists. Needed if Severed is
   shipped as a new `DS2DATn.DAT`.
3. **Converter:** per format, using the 360/PC pairs as test data.
4. **Loader DLL:** find the PDLC scan/mount path in the running PC exe and
   feed it the installed Severed folder or archive.
5. **Installer app:** STFS reader (done) → converter → install files + DLL.

## Scanner fix

`Disc 1\AvatarAssetPack` and `Disc 2\AvatarAssetPack` failed with "property
'Count' cannot be found". This happened on packages with a single file,
under Windows PowerShell 5.1 strict mode. Fixed.

---

# Round 2: archive contents and the exe

Source: second scans (archive entries listed and hashed) and
`deadspace2.exe` (Steam, SHA-256 `f72f15b8…1d7f`).

## 7. Archive name hash solved

The `BIGH` name hash is **sdbm** (`h = h * 65599 + c`, 32-bit) of the
**lowercase path with backslashes**, relative to the data root:

    ch01_hos\ch01_hos.toc  ->  0xC2B10B96

118 of 135 guessed chapter file names resolve on both platforms (the rest
are combinations that don't exist). Chapters on PC are split across
`DS2DAT6/7/8.DAT` exactly as on the 360 discs, multiplayer is in
`DS2DAT9.DAT`. None of Severed's paths (`pdlc1_ch01_mng\...`) exist in the
base archives.

So we can write a valid PC archive holding Severed's files under their real
names. The exe builds archive names with `%sDS2DAT%d.DAT`, so it numbers
them. Whether it also tries the missing `DS2DAT2`–`5` is what the probe DLL
checks.

## 8. PC formats are the 360 formats, little-endian

1,427 level streams (`.str`) and 83 tables of contents (`.toc`) exist on
both platforms under the same hash. Only 3 small text files are
byte-identical.

| Format | 360 | PC |
|--------|-----|----|
| `.str` | `ols3`, chunk tags `SHOC` `SHDR` `SDAT`, platform byte `04` | `3slo`, tags `COHS` `RDHS`, platform byte `03` |
| `.toc` | magic `9C BA 7B 28` | `28 7B BA 9C`; counts differ, so rebuilt rather than swapped |
| `.snu` | header fields big-endian, codec **3 = EA-XMA**, mostly 48 kHz | little-endian, codec **4 = EA-XAS** (471) or **7 = EALayer3** (459), 32 kHz |

In `.str` chunks the 32-bit fields are byte-swapped, while embedded strings
(e.g. `s:\asset…`) are unchanged. So conversion is schema-aware swapping,
plus re-encoding of anything platform-specific inside (textures, vertex
data, maybe shaders). The 360/PC pairs are the test data.

Audio: decode EA-XMA (vgmstream/FFmpeg can), re-encode as EA-XAS (an
ADPCM codec, simple enough to write an encoder for).

Other contents seen: the chapter list (`ch01_hos /FOLDER ds_2\ /STREAMLIST
ds_2.str /CHECKPOINT …`), a build/version file, and **Lua game scripts**.

Severed also ships its own `global_assets\global_assets_global.str`, which
differs from the base game's copy. The DLC overrides at least one base file.

## 9. The exe

- **Code is encrypted on disk.** `.text` and Solidshield's section are
  uniformly high-entropy, and the import table is a stub (one function per
  DLL) rebuilt at runtime. Static disassembly of the file is not possible.
  Readable data (`.rdata`, `.data`) is.
- **The DLC file types are registered in the PC build:** `.key`, `.pid`,
  `.lds`, `.add`, `.lvl`, `.dlm` and `pdlc` appear in `.rdata` among other
  resource extensions (e.g. `.lh2`). So the PC engine has handlers for
  every Severed descriptor file.
- The game imports `DINPUT8.dll`, `d3d9.dll`, `XINPUT1_3.dll`,
  `VERSION.dll`, `DSOUND.dll`, all usable as proxy-DLL entry points. The
  probe uses `dinput8.dll`.

## 10. Next steps

1. **Probe DLL** (`tools/probe`): log every file the game opens or probes.
   This shows whether `DS2DAT2`–`5` or any DLC location is looked for.
2. **Samples** (`tools/samples`): export matched PC/360 file pairs plus
   key Severed files, to write and test the `.str`, `.toc` and `.snu`
   converters against.
3. Then: archive writer (BIGH + sdbm) → try loading an unmodified PC file
   from a new `DS2DATn.DAT` → converters → loader DLL that points the
   game's PDLC code at the installed content.

---

# Round 3: probe log and sample files

## 11. Probe log

The probe ran without problems (all hooks installed, the game ran normally).
At startup the game tries **`DS2DAT0.DAT` to `DS2DAT12.DAT`** and opens
whichever exist; 2–5 and 10–12 are missing. **A new archive in one of those
slots is loaded with no exe changes.** Movies are loose files under
`movies\<lang>\`. The game never looked for a DLC folder or any DLC file, so
DLC discovery is the one piece that will need the loader DLL.

## 12. The PC game already knows the Severed level

The base game's level list (archive entry `#E4529CFE`, identical on PC and
360) contains:

    pdlc1_ch01_mng /FOLDER pdlc1_ch01_mng\ /STREAMLIST pdlc1_ch01_mng.str
        /CHECKPOINT initial XONTREALPR_CB22182_E50854D_v3 post_intro_inital ...

with every Severed checkpoint, matching `weller1.lvl`. What PC lacks is the
level's files and the menu entry.

## 13. Stream file structure

Each asset is a `SHDR` header chunk (type, IDs, uncompressed size, name,
source path, type name) followed by data chunks:

| | Xbox 360 | PC |
|-|----------|----|
| compressed data | `LZXD`: XMemCompress (LZX) frames | `Rpak`: EA RefPack |
| uncompressed data | `SDAT` | `SDAT` |

Decoders for both are in `tools/research/ds2`. They are cross-verified: all
14 Lua scripts decode to identical bytes from the 360 LZX and PC RefPack
data.

Severed's own streams:
- `dlc_support\level_select.str` (loaded on the main menu) holds one
  **`LH2`** asset. `.lh2` is in the exe's file-type table next to `.key`
  and `.pid`; this is almost certainly the Severed menu entry.
- `global_assets\global_assets_global.str` replaces the base game's copy
  with updated **Lua 5.0 bytecode** audio scripts (same on both platforms).
- `pdlc1_ch01_mng.str`: 453 assets (textures, VFX, TOB, materials, meshes,
  Havok, sound banks, Lua, NAV, LH2, …).

## 14. What converting each asset type takes

Payload comparison of every asset present in both PC and 360 samples (9
stream pairs, ~2,000 assets):

| Type | Result | Conversion |
|------|--------|------------|
| LUA | identical | copy |
| TOB | 100% match after 32-bit swap | swap every 32-bit word |
| tg4d (texture data) | 100% match after 16-bit swap | swap 16-bit words; **no untiling** |
| VFX, ANIM, RCB, LightTOC, APX, HKX, MetaModel | same size, 80–97% match after 32-bit swap | per-type layout (mixed field sizes) |
| tg4h (texture header), Material, Mesh, MeshVolatile | often different size | real format conversion |
| SBK (sound bank) | mostly 360-only (PC keeps most outside streams) | audio re-encode + repackaging |

## 15. Reusing the PC's own copies

Asset header IDs identify content: Severed assets with the same `(type,
name, IDs)` as a base-game asset have identical payloads (116/116 in the
samples), and the same asset carries the same IDs on PC and 360 (390/400).
Even against only six base-game streams, **116 of Severed's 453 assets
(19% of its data) are base-game assets**. The installer can take those
from the user's own PC archives, matched by header, with no conversion.
Against the whole game the share will be higher.

## 16. Next

1. Probe v2 + test archive: confirm an added archive overrides base files.
2. Full asset index of the PC archives and Severed: exactly which Severed
   assets need converting.
3. Converters in order of payoff: container (chunks, LZX → SDAT), TOB,
   textures, then the per-type layouts.

## 17. Test archive accepted

With a `DS2DAT2.DAT` written by `tools/archive/New-TestArchive.ps1` (6
entries copied from the PC archives), the game opened it in its normal
archive sequence (`DS2DAT0, 1, 2, 6, 7, 8, 9`), read its directory and ran
normally through the menu, a save load and gameplay. The archive format
written by our tools is accepted.

Which copy of a duplicated file the game uses is still open: probe v2 could
not hook `ReadFile` on Windows 11 (no hot-patch prologue: `6A 18 68 …`;
kernel32's export is a `jmp [ptr]` stub). Probe v3 adds trampoline and
stub-pointer hooks for that.

## 18. An added archive overrides the base game

Probe v3 hooked `ReadFile` (trampoline) and logged where each archive entry
was read from. With the test `DS2DAT2.DAT` installed, every duplicated file
was read **only from `DS2DAT2.DAT`**, never from the original copy:

| Entry | File | Original | Read from |
|-------|------|----------|-----------|
| `#16408156` | `frontend\frontend.toc` | DS2DAT6 | DS2DAT2 |
| `#F9E85989` | `frontend\frontend_global.str` | DS2DAT6 | DS2DAT2 |
| `#15C7731F` | `frontend\frontend.str` (20 MB) | DS2DAT6 | DS2DAT2 |
| `#16603703` | `global_assets\global_assets_global.str` | DS2DAT9 | DS2DAT2 |

When a file exists in several archives, the lowest-numbered archive wins.
So Severed can ship as `DS2DAT2.DAT`: its new files are found, and its
replacement `global_assets_global.str` takes precedence over the base
game's. No exe changes are needed to install the content.

## 19. How much of Severed the PC game already has

From the asset index (`tools/index`, `tools/research/reuse.py`): the PC
archives hold 290,383 asset rows (97,587 distinct); Severed's 162 streams
hold 60,828 rows, **20,169 distinct assets, 888 MB**.

| | Assets | Data |
|-|-------:|-----:|
| Identical asset already in the PC game: take it from the user's files | 13,286 | 473 MB (53%) |
| Same name as a PC asset, different content (Severed's own edit) | 3,291 | 313 MB (35%) |
| New in Severed | 3,592 | 102 MB (12%) |

Asset IDs are platform-independent for every type except APX (checked on
base-game pairs: e.g. Material 80/80, Mesh 78/78, HKX 31/31 share IDs). So
"same name, different IDs" really is a different version, and those assets
need converting too. **Converter workload: about 6,900 assets, 414 MB**:

| Type | To convert | Notes |
|------|-----------:|-------|
| Material | 4,327 | often a different size on PC: needs format work |
| SBK (sound banks) | 518 | XMA audio; PC packages most banks differently |
| VFX | 444 | ~92% plain 32-bit swap |
| tg4h + tg4d (textures) | 242 each | data: 16-bit swap; header: format work |
| Mesh / MeshVolatile | 215 / 180 | vertex data |
| MetaModel | 170 | |
| SimGroup | 159 | |
| HKX (Havok) | 140 | |
| NAV (navigation mesh) | 101 | new type, no PC/360 pair in samples |
| BNK, SMB, TOB, Graph, RCB, LUA, PNG, LH2, ISM, ANIM | ~200 | TOB is a plain 32-bit swap, LUA is copied |

Stream layout rules (both platforms): chunks are 4-byte aligned, never cross
a 128 KB boundary, `FILL` chunks pad to the next boundary, files are a
multiple of 128 KB.

## 20. Converter status (from the full PC/360 pair export)

Method: for each type, a 360 -> PC converter is scored against every
exported pair (`tools/research/score.py`, `learn_*.py`): exact byte match
with the real PC asset, or within rounding for re-packed vertex data.

| Type | Pairs | Result | Severed coverage |
|------|------:|--------|------------------|
| LUA | 46 | 100% exact (identical bytecode) | all |
| TOB | 501 | 100% exact (32-bit swap) | all |
| tg4d (texture data) | 315 (samples) | 100% (16-bit swap) | all |
| tg4h (texture header) | 16,768 | 99.6% exact; rest are different PC images | all |
| Material | 4,054 | 100% exact | all 5,553 distinct Severed materials |
| VFX | 8,807 | 99.4% exact (97.4% held-out); misses are float rounding | all 1,580 |
| Mesh | 4,746 | 90.5% within rounding of the 2,793 pairs with identical structure (rest: PC re-exported differently) | all 1,065 distinct Severed meshes |
| MeshVolatile | 3,412 | 84% exact or within rounding of 2,780 matched pairs | all 851 |
| MetaModel | 1,978 | 100% exact | all 584 |
| SimGroup | 1,291 | base-game format worked out (below); Severed uses a newer format with no PC example | needs the PC field layouts (probe v4) |
| HKX, NAV, SBK, BNK, SMB, Graph, RCB, LH2, PNG, ISM, ANIM | | not started | |

Mesh structure from the DS1-3 Modding Toolkit by 4Kodda (Nexus mod 101; used
as a format reference, no code copied): DataTable1 at header 0x50 (0xC0
bytes per draw table: name, vertex count/size/offset, face count/offset,
primitive type, bone palette, vert_id pool, UV size), DataTable2 at 0x68
(buffer descriptors size/count/format/ptr; ptr >= local UV offset at 0x9C
means the buffer is in the MeshVolatile, which directly follows its mesh
in a stream file). PC encodings: normal = floor((c/511 + 1) * 127.5) from
the 360 DEC3N; tangent from 360 signed bytes (skinned 0x20 records: x y z
w, handedness byte flipped; 0x14 records: stored w z y x); bone indices
kept; weights u16 swapped; a DT1 face-count field the 360 stores as
count+1. Gibbed.Visceral (zlib licence) documents stream sets, BIG
archives, texture headers and SimGroup.

Material: PC shader passes follow a deterministic table per 360 shader
setup (60 setups, learned from the pairs), plus parameter copies the PC
shaders need. VFX: components (`.prt`, `.fnc`, `.snd`, ...) with learned
per-word byte permutations; one 16-byte union field (name / raw ID /
hashes) decided per record.

Mesh notes so far: header `EAGM` v50, platform word 1 (360) -> 3 (PC);
header pointers to tables (0x4C 0x50 0x54 0x60 0x68 0x6C 0x78 0x7C; total
size at 0x9C). Stream descriptors (size, count, stride, type, flags,
offset); offset 0 / past the end = buffer in the companion
`<name>.volatile` (MeshVolatile) asset. Vertex slots: floats swap; normals
360 DEC3N -> PC UBYTE4N; tangents 360 signed bytes (reversed) -> PC
UBYTE4N; index buffers u16 swap. PC values were packed from the source
data separately, so re-packed normals match within rounding, not exactly.
Some meshes have several stream tables (LODs); the full table layout is
not worked out yet.

## 21. MetaModel

`MMdl` v14: 8 table pointers at 0x34 and 8 u16 counts at 0x58. Fixed
records: table 0 (32 bytes), 1 (48), 2 (12), 3 (24), 4 (12), 5 and 6
(36); each table is followed by u32 pointer lists; the string table (raw)
starts at the lowest name referenced by tables 1, 5 and 6; table 7 is the
trailing float data. All fields are 32-bit except (count, kind) u16 pairs
at fixed record positions, and bools: a table 3 value of type 1, and a
table 4 value whose table 2 entry has kind 1, are bytes kept as stored.
`ds2/metamodel.py`; 100% exact on all pairs.

## 22. SimGroup: two formats

A SimGroup (level objects: triggers, scripts, props, lights, ...) has a
header (Gibbed.Visceral `SimGroup/FileHeader`), a hash list, 0x44-byte
object records and, 16-aligned after the header, a data block.

Base game (PC and 360), block `91C8773C`: a self-describing property tree.
Type-name table of (hash, count); 12-byte node records (hash, u16 type-name
index, u16 child count, offset to a u16 child list); 12-byte properties
(name hash, u16 count, u8 type, u8 index, value). Values are inline
(float 0, ints 1/2/22, hashes 8/10/11, bools 5/7 as bytes) or offsets
relative to the value field (strings 1/3/5/16/17, 16-byte asset
references 12, vectors 13/14/15). Node hashes of the groups are sdbm over
the member type-name hashes in native byte order, so they differ between
PC and 360 and can be recomputed. The hashes of nodes holding a type-12
reference also differ per platform; their formula is not found yet.

Severed (all 160 SimGroups), block `011795D9`: never used by the base game
on either platform. Type-name table of (name hash, class version); per
object a packed record of the class's fields, e.g. LuaAudioScript =
{u32, string, string, asset ref, string data}, a string being (sdbm hash,
0, offset relative to that field) and an asset reference 16 bytes of
hashes. The 346 class and type names all exist as strings in the PC exe
(so the PC engine has these classes), but which fields are bytes, u16 or
u32 is not in the data itself: about 5,000 record words are byte-packed
bools and about 10,000 are ambiguous. The probe's reflection scan (v4,
F10) reads the PC engine's class layouts from memory to settle this, and
also shows whether the PC exe knows the `011795D9` marker.

### Reflection scan result

The PC exe's code contains the `011795D9` marker 17 bytes after
`91C8773C` (one occurrence each): the PC engine reads both SimGroup
formats. Class descriptors are static objects in `.data`: vtable
`01B1E648`, name pointer, sdbm(lower-case name), version, ..., field list
on the heap (a parent-class pointer, then 16-byte entries {type info,
field descriptor, u16 offset, u16 index, u16, u16}). Field descriptors
(`.data`, 20 bytes) hold name, hash and the same type codes as the base
format (e.g. 0x11 string, 0x0C asset reference). LuaAudioScript: flags at
0, strings at 4 and 0x10, asset reference at 0x1C, size 0x2C, exactly as
in the Severed records. Flag sets and enums have their own descriptors
(vtables `01AA6C80`, `01AA6C68`). Probe v5 (F11) dumps the complete field
lists.
