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
| SimGroup | (no PC example of the Severed format) | converted with the PC engine's own class layouts; output re-validated (all 21,712 message strings, all 1,435 group hashes) | all 160; 27 records of 8 classes the PC exe lacks |
| BNK (animation banks) | 147 | 99.99% of words right on held-out files (38/73 files exact); remaining misses are rare node layouts | all 100 |
| NAV (navigation) | 770 (paired by name: .xen/.win) | exact (770/770 since the header sums are recomputed, section 41) | all 101 |
| HKX (Havok physics) | 1,684 | 832/842 held-out files byte-exact (rest: PC re-exported with other values) | all 515 |
| SBK (sound banks) | 80 (second export) | metadata 78/80 exact (other 2: different sample sets); sdat rebuild exact; samples EA-XMA -> EA-XAS (26-60 dB SNR) | all 531 |
| RCB | 358 | 108/179 held-out files exact, 99.91% of words (relocation-table blocks, swap default) | all 54 |
| SMB | 167 | 158 exact (32-bit + 0x0016 record headers as u16 pairs + names) | all 31 |
| LH2 (string tables) | (structure check) | header/IDs/offsets 32-bit, text raw; a converted 360 table parses on PC layout, 6,649/6,873 shared strings identical | both (menu text, Severed text) |
| ANIM | 51 | 99.93% of words held-out (position template) | 1 |
| PNG | | standard PNG, copied | 2 |
| Graph | 122 | 56/61 held-out files exact, 99.97% of words; all 122 with the full model (region model) | all 15 |
| ISM (impact tables) | 6 | 3/3 held-out exact, 6/6 (region model) | 1 |
| LightTOC, VariableDictionary | 1 / 1 (different content) | layout from the pair (0xA0-byte light records; word table + strings) | 1 / 1 |

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

### Descriptor dump result (probe v5)

All 14,265 Severed records name a class whose version equals the PC
engine's. A record is the class's own fields at the engine's offsets
(base classes add none here), followed by string data. Validated: all
17,665 non-empty message fields (type 0x11) point at a string whose
sdbm(lower-case) equals the stored hash. Field encodings by type code:
0 float, 1 int / enum / flag set (4 bytes), 2 int, 3 and 4 16-bit, 5 byte
(also 1-byte flag sets), 7 bool (byte), 8 colour (4 bytes), 0x0A hash,
0x0B interface reference, 0x0C asset reference (4 x u32), 0x0D vec3,
0x0E vec4, 0x0F matrix (16 floats), 0x10 string offset (u32 relative to
the field), 0x11 message (hash, 0, offset relative to the offset word),
0x13 fixed inline array (type info: count, element type). Flag-set
descriptors give their storage type at word 6. v5 lost parts of .data and
cut long field lists; 305 classes decode, 66 Severed classes need v6.

### SimGroup converter (probe v6)

`tools/research/reflect/export_schema.py` turns probe v6's dump into
`ds2/simgroup_schema.json` (478 PC classes: version, size, fields; arrays
carry count and element type; type 0x16 = embedded struct with its class).
`ds2/simgroup.py` converts the Severed format: header words 32-bit except
the u16 counts at 0x14-0x1B; block header u16 pair at +0x0C; record table
(u32 x3, u16 x2); records field by field; strings raw; group hashes
recomputed as sdbm over the members' class-name hashes in little-endian
order (verified on all 1,435 Severed groups in 360 order). Every non-zero
byte of every record lies in a known field. 8 Severed classes (27 records:
e.g. an upgrade-node equip script, an end-of-game UI message) do not exist
in the PC exe; they are converted heuristically (32-bit words up to their
strings) and may have to be dropped if the PC game rejects them.
Colours (type 8) are kept as 4 bytes; unverified.

### Severed-only classes

8 class names in Severed's SimGroups are not in the PC exe (27 objects).
Fitting every PC layout to their records (all message strings resolve, no
non-zero byte outside a field) identifies five as DLC copies of PC
classes, never used themselves by Severed, so the converter re-labels
them (`REMAP` in `ds2/simgroup.py`):

| Severed class (hash) | Objects | PC layout | Notes |
|---|---:|---|---|
| AC69505E | 5 | ShipStore v11 | store kiosks; the PC class already has the DLC item fields (PDLC item, upgrade node, `m_enablePDLCScanning` = 1) |
| 8F69BA55 (SaveKioskExt) | 9 | SaveKiosk v2 | save stations ("Save Menu") |
| AA6A826D | 4 | SimplePressAndHoldSwitch v8 | quarry / mining camp door switches |
| 9F75D02A | 1 | RigAnnouncementSystem v3 | RIG message VFX setup |
| A1C89AA7 (UIEndOfGameDataExt) | 1 | UIEndOfGameData v2 | end of the DLC: fade, credits after 18 s; 20 extra bytes, all zero |

Left: 2B747EB6 (3 objects, on message `equip_player_upgrade_nodes`: weapon
`PulseRifle`, nodes Capacity, Capacity2, Damage, Damage3, Reload2,
AltDamage, AltDamage2, PR12, PR21, PR23; Gabe's pre-upgraded rifle; no PC
class does this), 8F917978 (3 objects, two hashes) and 742ECD09 (1 object,
one u32). Behaviour of the re-labelled objects (e.g. whether the store
lists Severed's items) needs the in-game test.

### Gabe's upgraded Pulse Rifle (360 Severed save)

A 360 Severed starter save (STFS CON package, `ds2/stfs.py`; inside, an
`MC02` save) holds the upgrade state as 12-byte records (weapon hash, node
hash, 1), sdbm of lower-case names. The Pulse Rifle (`pulserifle`) has
exactly the 10 nodes the Severed-only equip object lists: capacity,
capacity2, damage, damage3, reload2, altdamage, altdamage2, pr12, pr21,
pr23. The PC exe exposes the upgrade system to Lua (tolua bindings:
`GetUpgradeManager`, `UpgradeManager:Upgrade`, `Connect`, `UpgradeValue`,
`DebugFillUpgradeNode`; script names `player_upgrades.lua`,
`demo_player_upgrade_levels.lua`), so the equip can be redone from a level
Lua script responding to `equip_player_upgrade_nodes`; the call signatures
still need working out.

## 23. Severed's menu entry (360 footage) and the PC's episode select

360 flow with Severed installed: main menu -> single player -> **episode
select** ("Dead Space 2" / "Dead Space 2: Severed", with a description
line) -> brightness -> loading. Severed's
`dlc_support/level_select.str` (LH2 `string_ids_frontend`) holds that
entry's text in 7 languages ("Dead Space 2: Severed", the description,
"Difficulty setting not available for this episode.", save-slot name
"Severed, chapter", `weller1_map_name`, `weller1_save_chapter_xen`).

The PC exe has the same screen: next to the front-end code it holds the
built-in episode entry (level `ds_2` / `ds_2.str`, `$ui_episode_ds_name`,
`$ui_episode_ds_help`, picture VFX `XCENTKOWSK_C9C50BC_08B592A_v3`). So the
episode list exists on PC with only the base game in it; the menu hook
only has to get Severed (the `weller1.*` DLC descriptor files) into that
list, not build a new menu.

### Reference from 360 footage (Let's Play, first 10 minutes)

- Store kiosk: the normal store screen (Shop / Inventory tabs, credits,
  nodes) listing the usual weapons (Plasma Cutter, Javelin, Force Gun,
  Seeker, Pulse Rifle) plus unlocked extras (Hand Cannon, Patrol Seeker):
  the PC `ShipStore` behaviour, as the re-labelling assumes.
- Bench: Plasma Cutter, Force Gun, Pulse Rifle, RIG, Stasis Module;
  "Respec ability unlocked" pop-up on first use.
- Gabe's Pulse Rifle at the first bench: Damage 7, Capacity 100,
  Reload 1.2, Alt Fire 5 (the target for the PC upgrade fix); it sells for
  53,500 credits.

## 24. BNK animation banks

Not audio: animation banks. Word 0 is the offset of a relocation table at
the end (big-endian offsets of every pointer field, ending in 0). The
compressed animation data is byte-identical on both platforms; node
structures (u32 fields, floats, (u8, u8, u16) node headers, names, '_'
padding) are swapped. `ds2/reloc.py` splits the file into pointer-target
blocks, types each block by (parent's pointer offset, pointer offset,
block kind: first byte, or ('h', codec) for animation data starting with a
hash and a codec word), learns a template per type with fallbacks to
coarser keys, keeps names raw, swaps pointers and the table. Severed: all
11,403 blocks of its 100 banks have a template (`learn_bnk.py`).

## 25. SBK sound banks

Header `sbnk` v209: metadata size, data size, data offset (u32), metadata
mostly u32/float with a few byte-packed words (e.g. `50 10 00 01`). Data
section `sdat`: count, then 16-byte entries (index, 0x0313BABE, offset
from `sdat`, 0xFEEDFEED), then EA "EAAC" sample headers + audio. Header
word 1: version:4 codec:4 channel config:6 sample rate:18. 360 samples are
codec 3 (EA-XMA); every PC sample is codec 7 (EALayer3 v2), sometimes at a
different sample rate (8 kHz on 360 -> 16 kHz on PC). So Severed's sound
banks need decoding XMA and encoding EALayer3 (or another codec the PC
decoder accepts).

Converter (`ds2/sbk.py`, second export: 80 distinct pairs). The section
offsets at 0x24-0x44 are relative to 0x18: A end, N, B, C, ?, E, E size,
G, H. Byte order per section: A records (offsets in the list at 0x68)
have byte-packed words at +4 and +0x1C (raw); the float tables from C to
E start each sub-table with a u16 count (`000N0000` -> u16 pair); E holds
8-byte entries {u16, 2 raw bytes, u32}; H holds 0x18-byte entries whose
last word is a hash stored byte-reversed (same bytes on both platforms);
everything else is plain 32-bit. Apart from the data sizes at 0x0C/0x14
the metadata is otherwise identical on both platforms, so the sample rate
and length live only in each sample's own header. Samples sit back to back
after the sdat entries, each one EAAC header plus a single flag-0 block
(long ones: several). Converted samples: decoded from EA-XMA and encoded
as XAS (codec 4) at the 360 rate; banks grow about 2.4x (35 -> 86 MB for
all of Severed). Whether the PC bank player accepts codec 4 (its streams
do) is to be checked in game; fallback is PCM.

## 26. NAV navigation collections

Names end in `.xen` (360) / `.win` (PC), so the asset IDs differ: id1-3 =
360 id + (sdbm(PC name) - sdbm(360 name)), id4 = 360 id4 - 1 (769/770; one
borrow case). Payload: 32-bit throughout except a constant 128-byte table
(identical in all 825 occurrences; kept), unused pointer slots
(0xFFFFFFFF followed by 2 or 0x1B -> 0; 1,607/1,607) and a per-collection
sum in each (nested) header (`00000002 <size> <sum>`), recomputed on
conversion (section 41). `ds2/nav.py`.

## 27. Audio decoding and encoding

PC streamed audio (.snu) uses codec 4 (EA-XAS v1, 4-bit ADPCM) or 7
(EALayer3); sound banks use 7. So the PC decoder plays XAS: Severed's
EA-XMA (codec 3) is decoded and re-encoded as XAS. `ds2/eaaudio.py` parses
EAAudioCore headers/blocks, turns EA-XMA blocks into standard XMA2 (per
1/2-channel layer: blocks hold `size*4` + 0x800-byte XMA packets) for
ffmpeg's xma2 decoder, and decodes XAS. Check: a 360 stream decoded from
XMA and the PC's own XAS encoding of the same stream correlate at 0.998,
sample-aligned. `native/xas_enc.c` encodes XAS (per 32-sample group: all
4 coefficient pairs x 13 shifts in closed loop). PC XAS streams use blocks
of up to 27 frames (2,060 bytes); bank samples are one block. SNU
container: u8 3, u8 0, u16 (1/2), u32 (platform order), u32 offset of the
audio data (0x20), u32 0, then the big-endian SNR header at 0x10.

## 28. HKX Havok packfiles

Havok 6.5.0 packfiles: 0x40 header (layout rules byte 1 = little-endian
flag: 0 on 360, 1 on PC), section headers (name, start, local / global /
virtual fixups, exports, imports, end), `__classnames__` (u32 signature,
0x09, name), `__data__`. Virtual fixups give each object's class; local and
global fixups give every pointer. `ds2/hkx.py` types objects by class and
pointed-to blocks by (class, member offset) and learns templates with the
shared `ds2/blockmodel.py`, which also learns 8-byte values (Havok property
values, u64) and keeps names only through their own blocks (alignment
padding holds stale text that the PC tools swapped as u32). Held-out:
832/842 files byte-exact, 99.76% of words. All 515 Severed HKX files
convert with a template for every block.

## 29. Graph and ISM files

Both are a fixed header (Graph 0xA0, ISM 0x20) followed by arrays that
the header points to (Graph offsets at 0x20-0x48, 0x50, 0x58, 0x60, 0x68,
0x70, counts as u16 pairs at 0x0C/0x2C/0x3C; ISM offsets at 0x10-0x1C).
The arrays mix floats, u32, u16 pairs and byte fields (Graph nodes: 0x30
bytes with a u16 pair and flag bytes; edges 0x30 bytes). `ds2/regionmodel.py`
cuts a file into the regions the offsets point to and learns each unit's
byte order by (region, position mod stride), choosing each region's
stride by leave-one-file-out prediction; the model is JSON
(`ds2/graph_model.json`, `ds2/ism_model.json`, `learn_region.py`).
Checked on all Severed files: converted header offsets read the same.

## 30. Writing PC streams, TOCs and the archive

Stream files on both platforms are read in 128 KB sectors: no chunk
crosses a sector boundary, data that does not fit is split into several
chunks at the boundary, FILL pads a sector when the next chunk does not
fit and pads the last sector. PC streams mix Rpak (RefPack) and SDAT
chunks of any size, so the converted streams are written with SDAT only
(`ds2/streamwrite.py`). Checks: re-writing the PC frontend and ch01_hos
streams gives the same assets; 360 asset headers convert to the exact PC
headers (flags, IDs and alignment are the same; source paths `.xen` ->
`.win`). File header word 3: 360 `00 02 04 01`, PC `02 00 03 01`.

TOC (`ds2/toc.py`): magic 0x9CBA7B28, version 10, u16 stream count, u16
name count, two u16; 20-byte stream entries {name entry, total
uncompressed size of the stream, 4 byte fields, u32, dependency list};
hash-sorted name entries {hash, string offset}; dependency lists; names.
Converted 360 TOCs equal the PC ones once each stream's size is filled in
(4 pairs with the same stream list). The sizes come from the converted
streams.

`ds2/build.py` converts the whole Severed folder; `ds2/bigarchive.py`
writes the DS2DAT archive. Severed's other files: `.lds .key .pid .lvl
.dlm` are text, `.add` lists each stream with a 32-bit value that is not
a CRC-32 of the file (not needed unless the console DLC loader is used),
`spa.bin` is the Xbox dashboard achievement file (not needed), `.vp6`
videos are platform-neutral.

`global_assets\global_assets_global.str`: Severed's copy replaces the
base game's with updated Lua audio scripts. On PC the installer should
patch the PC's own copy (swap in Severed's Lua assets, identical bytecode
on both platforms) rather than replace the file.

## 31. First in-game test (chapter 1 override)

The test archive loaded: the game opened DS2DAT2.DAT (424 entries) and
read our `ch01_hos\ch01_hos.toc` (Severed's TOC) and patched
`global_assets\global_assets_global.str`, but New Game played chapter 1's
intro (Isaac in the chair) and the player fell into the void. Probe log:
the PC loads a level from `<level>\<level>.toc` plus
`<level>\<level>_streamsets.str` (a SimGroup, e.g.
`{54B1E16B-0001-7400-5354-5245414D5345}` from
`levels\ch01_hos\ch01_hos\streams\ch01_hos_streamsets.simgroup.bin`) and
the episode files `ds_2\ds_2.toc`, `ds_2\ds_2.str`,
`ds_2\ds_2_global.str`; chapter 1's own stream sets then streamed chapter
1's sections (DS2DAT9) and none of Severed's streams were read. The level
list (#E4529CFE) was not read at all in that session, so its override did
nothing. Severed ships no stream sets file (neither its streams nor its
package contain one); the console DLC path (`.lds .lvl .key .pid .dlm
.add`, all names present in the PC exe) loads without it.

The exe's code section is encrypted on disk (Steam wrapper), so no code
references to those strings can be found statically; the loader path has
to be found at runtime (file activity, return addresses) without dumping
code.

Next test: chapter 1's stream sets replaced by an empty stream.

Second run (chapter 1 stream sets blanked): a level loaded and was
playable (prologue Isaac, enemies, an audio log), but only three entries
came from our archive (TOC, empty stream sets, global assets); every
level stream came from the base archives, so it was base content. The
PC's level entries appear to be built into the exe (the level list file
#E4529CFE was never read; the chapter 1 entry's episode files
`ds_2\ds_2.toc/.str/_global.str` were). Next test: Severed's own
top-level files (`pdlc1_ch01_mng\pdlc1_ch01_mng.toc/.str/_global.*`) also
under the `ds_2\ds_2.*` names.

## 32. The episode list and how the console added Severed

A retail build of `deadspace2.exe` without the Steam wrapper (same build:
`.rdata`/`.data` match the Steam exe page for page, only the Steam exe's
code is encrypted; fixed base 0x400000) lets the code be read statically.
Read-only analysis, nothing patched on disk:

- The engine registers a loader per file extension: `.lds` (0x00414380,
  manager [0x02021410]), `.rep`, `.add` ([0x02021418]), `.lvl`
  (0x00A54440, manager [0x020213F0], level count at +0x8528), etc. So the
  DLC descriptors are ordinary resources.
- The front end (constructor 0x00AA09E0, singleton [0x0201C0E4]) keeps
  the episode list at +0x980: a vector of 0x68-byte entries (+0x00 name,
  +0x10 description, +0x20 folder, +0x30 stream list, +0x40 extra, +0x50
  start checkpoint GUID, +0x60 flags, +0x64 unlock key; strings are 16-byte
  objects with the text pointer first). The constructor adds the built-in
  entry: `$ui_episode_ds_name`, `$ui_episode_ds_help`, `ds_2`,
  `ds_2.str`, "", `XCENTKOWSK_C9C50BC_08B592A_v3` (chapter 1's initial
  checkpoint).
- AddEpisode 0x00A93520 (thiscall, 8 arguments: name, description,
  folder, stream list, checkpoint, flags, unlock key, extra) is called only
  from 0x00A99C00, a message handler taking a level descriptor - the
  `.lvl` path. Severed's `weller1.lvl` has exactly these fields: name
  `$weller1_map_name`, description `$weller1_map_desc`, flags 0, unlock
  key 0 (always unlocked), folder `pdlc1_ch01_mng`, stream
  `pdlc1_ch01_mng.str`, checkpoint `XONTREALPR_CB22182_E50854D_v3`, save
  chapter name, "no difficulty" text, save icon suffix.

So the menu hook only has to make that one call (probe 7: F9). The
episode's display text (`$weller1_*`) is in Severed's
`dlc_support\level_select.str`, which the console loads in the front end
through `weller1.lds` (load mask 1 = front end).

## 33. Severed from the episode select (probes 9-10)

Probe 9 hooks the front end constructor in memory (found by byte pattern
once the Steam wrapper has decrypted the code) and calls AddEpisode on the
game's thread right after the built-in entry: "Dead Space 2: Severed"
appears in the episode select. (Calling it from the probe's own thread, as
probes 7/8 did, hangs the game.) Choosing it loads Severed's own files from
the test archive: `pdlc1_ch01_mng\pdlc1_ch01_mng.toc`,
`pdlc1_ch01_mng_global.str` and all of `pdlc1_ch01_mng.str`, then the
game crashed in the routine that registers a loaded asset (null pointer:
the asset's type info). The only asset type in that stream the PC never
uses is PNG: `weller1_ch1.png` / `weller1_ch2.png` from
`shared\ui\icons\xenon\`, the Xbox save game icons. They are now left out
of the PC streams (`build.DROP`; the test script strips them from earlier
output and fixes the TOC sizes).

Without the PNGs Severed loads without crashing, but into an empty black
level (pause menu works). After `pdlc1_ch01_mng.toc/_global.str/.str` no
level section was read. What the exe shows:

- The base game's stream sets are loaded from a fixed list in the exe
  (0x01C30434: ch01_hos ... ch11_mtb, `%s\%s_streamsets.str`).
- The level start routine (0x0042C600) checks whether the level folder
  contains "pdlc": DLC levels skip that list and call the `.lds` manager
  (load mask), then request each stream of the episode's stream list
  (`folder\stream`) through 0x0074BDD0.
- Severed's StreamSet objects (182) are inside its main level SimGroup
  (`pdlc1_ch01_mng.simgroup.bin`); their stream references are the
  section SimGroups' GUIDs (4 words; GUID text prints words 3-4 as bytes).
  The start checkpoint (`XONTREALPR_CB22182_E50854D`) is object
  52CB2218 2E50854D 'ONTR' 'EALP' in that SimGroup.
- The `.add` values are not sdbm/CRC/FNV of the stream names, GUIDs or
  files.

Probe 11 logs every stream request to see what the StreamSets ask for.

Control run (base New Game, probe 11): the base game does not request its
level sections through 0x0074BDD0 either; at level start it requests all
ten `chXX\chXX_streamsets.str` (stream-sets mode: request(path, 0.0, 0, 0,
0)) and `ds_2\ds_2.str`, then sections stream by another route. In
Severed only `pdlc1_ch01_mng.str` and `player_bnk.str` were requested and
no section was ever read. In the base game the checkpoint objects live in
the stream sets SimGroup (e.g. chapter 1's `initial`
4BC9C50B C08B592A 'CENT' 'KOWS', stored as 4 swapped words like Severed's
references); in Severed they are in the level SimGroup. The `.add` values
equal the TOC's stream name hashes. Experiment: probe 12 requests
Severed's level SimGroup as a stream sets file at level start.

Probe 12: `pdlc1_ch01_mng_streamsets.str` (the level SimGroup) was
requested in stream-sets mode and read, still no section loaded. The PC
exe does handle the packed SimGroup block (dispatcher 0x0085D090: 0x011795D9
-> 0x0085C110, 0x91C8773C -> 0x0085D020, anything else int3). Probe 13
logs each block load and whether the loader accepted it, to see whether
Severed's converted SimGroups are rejected.

Probe 13: every SimGroup block loads "ok", Severed's too (main level
1,598 records twice, global 20 records). Base vs Severed after level
start: the base game reads a 7 MB stream (#A1BA05E4) before
`player_bnk.str` and then streams sections; Severed stops after
`player_bnk.str`. Severed's global SimGroup holds its player suits: 11
`Uniform` objects (+ UniformRegistry, PlayerDecompressionInfo, ...). The
Uniform class (version 9, 1,056 bytes, 133 fields, descriptor 0x02098B78)
is in the PC exe but its field list was not in the descriptor dump, so
those records were converted by guesswork; a wrong suit (e.g. its stream
GUID) would leave no player and an idle level. Probe 14 logs the layout.

Probe 15 logged the Uniform layout (133 fields, now in
`simgroup_schema.json`). Severed's 11 suits now convert by layout ("PDLC
Weller Suit", "Security Suit", ...); the earlier guesswork differed only in
three bool fields per record (stream GUID etc. were right). A suit's
`CMD_SetUniformStreamGUID` (interface reference) equals header word 0x2C of
its suit stream's SimGroup (Weller suit 0xBDD2DA83 ->
`uni_pdlcsecurityweller.str`); not an sdbm of the stream name. Probe 16
logs every file name the game hashes, to find what Severed's level start
asks for that is missing.

Probe 16: the hooked name hash only sees UI names, not file paths. But the
Severed run played the player's heartbeat and asphyxiation breathing: the
player spawns, in empty space, because no section streams. A stream's ID
(the TOC name hash, and what a suit's UniformStreamGUID / StreamSet refers
to) is word 0x2C of its SimGroup header. SimGroup packed layout detail:
header 0x08 = object hash list (u32 per object, = record table hash), 0x0C
= object entries (0x44 bytes: +4 offset of the object's hash in that list,
+8 GUID); so the record of an object is (entry[+4] - 0x3C) / 4. The start
checkpoint (record 1289, default) points at StreamSet 52CB2218 2E50854E
(record 1290): Set1-4 + Set24 = drill_tunnel_01, drill_tunnel_02,
drill_cavern_01, drill_saferoom, doors_mng_folderstream (StreamSet GUIDs
print as {w0-w1lo-w1hi-...} and match the section SimGroups' names).
Probe 17 requests those sections directly to see whether converted level
sections load and render.

Probe 17: requesting the start sections at level start loaded
`drill_tunnel_01`'s SimGroup (44 records, ZoneRender/props/components) right
after the main level SimGroup, then crashed in ZoneRender setup (null zone,
exe+0x3EE6A1 called from the CMD_SetFilterMask/ZoneRenderFlags handler):
the sections came before the main level stream was set up. Probe 18 queues
the request on F9 in the black level and runs it on the game thread.

Probe 18: requesting the start sections from the game thread after the
level was up crashed the same way. The null is the global zone manager
(0x0204D554, list at +0x5C/+0x60/+0x64), which the level's `ZoneWorld`
object (class with m_MaxManagedZones, fog, clip distances) sets up.
Severed's main SimGroup has its ZoneWorld, but it never activated - nor did
its StreamSets: the objects of the main level group are not being set up.
That group also holds the 5 records of the 3 Severed-only classes the PC
lacks (2B747EB6 Pulse Rifle pre-upgrade x3, 8F917978, 742ECD09). They now
become blank `NavFolder` objects (`simgroup.NEUTRAL`); the test script
re-converts the affected SimGroups.

## 34. Level collision: hkpStorageExtendedMeshShape (crash after sections streamed)

With the Severed-only SimGroup classes neutralised, sections streamed and the
game then crashed in Havok (exe+0x1096884, an hkArray append into a null data
pointer, called from hkObjectInspector). Every Severed level collision file
(599 HKX objects) is an `hkpStorageExtendedMeshShape` with
`...MeshSubpartStorage` / `...ShapeSubpartStorage` objects, and the export
held only one PC/360 pair of that class, too few for the learned model, so
they were converted with the generic template (bytes and u16 fields swapped
as words).

These classes are now converted from Havok's own reflection data. The
class registrations in `.text` (`push name; mov ecx, cls; call 0x4F85D0`,
after pushes of numMembers, members, 0,0,0,0, objectSize, parent) lead to the
static hkClassMember tables: 24 bytes each, {name*, class*, enum*, u8 type,
u8 subtype, i16 cArraySize, u16 flags, u16 offset, attributes*} (every
name resolves). The layouts, with parents and the structs they use, are in
`tools/research/ds2/hkx_classes.json`. `hkx.convert` walks those objects
member by member (u16/u32/u64 by type, enums by storage type, bytes as
stored, arrays followed through the fixups). It reproduces the one base-game
PC file byte for byte. In all Severed shapes, the array sizes, capacities,
vertices and indices (all 32-bit, every one below its vertex count) read
correctly.

## 35. Level geometry: triangle strips (stretched / spiky world)

After the collision fix the intro cutscene played and the level loaded with
Gabe's suit, the HUD and menus working. All level geometry, though, was
long stretched spikes. Two causes, both in the mesh draw tables (DT1):

- DT1 +0x3C (the u16 called `lod_type` earlier) is the Direct3D primitive
  type, followed by a u16 index count. Xbox 360: 4 = triangle list,
  6 = triangle strip. PC Direct3D 9: 4 = list, 5 = strip, 6 = triangle
  *fan*. The level meshes (`opt_model*`, `lodmodel`: 26,024 tables in
  Severed) are strips, and keeping the 6 made the PC draw them as fans.
- The 360 strips restart with index 0xFFFF. D3D9 has no primitive restart,
  so the PC read it as vertex 65535. The PC files join the strips with
  degenerate triangles instead (`ds2/strips.py`). This reproduces all
  9,150 restart tables of the base-game pairs exactly.

Joined buffers are longer. The tables of a mesh share an index buffer
(DT2 entry `00020200`; DT1 +0x30 index count, +0x34 start index, +0x88
pointer to the table's first index). The PC grows the buffer in place
and moves everything after it. We instead put the rebuilt buffer after
the mesh's own data and leave the old space zeroed. Only these fields
depend on the mesh's length:
- header 0x9C, the mesh size (DT2 pointers into the MeshVolatile are
  relative to it);
- header 0x0C, the total size;
- the DT2 volatile pointers.

DT1 +0xAE becomes the 360 value - 1 (as in the PC files).

DT1 +0x8C points to a per-table grid:
- 3 vectors (bounds);
- u16 nx, ny, nz, reference count, cell count;
- the references (positions of runs in the table's strip);
- cell count + 1 offsets.

The u16 part was being swapped as 32-bit words. The header, offsets and
bounds now match the PC files exactly. The references are carried through
the strip join, but the PC files' grids were rebuilt by their own tools,
with other runs, so their values are not reproducible.

On the base-game pairs, every converted strip table draws exactly the
PC's triangles with the PC's winding, and the volatile streams keep their
places.

Mesh relocation table (found from the crash in the first strip test): header
0x48 = count, 0x4C = offset of {u32 field offset, u32 value} pairs, one per
pointer field (header 0x20 0x4C 0x50 0x54 0x60 0x68 0x6C 0x78 0x7C, DT1 +0x00
+0x20 +0x44 +0x84 +0x88 +0x8C, DT2 +0x0C). The loader (exe 0x7C4B90) writes
each value back into its field (value < header 0x0C: mesh + value, else
volatile base + value - header 0x0C). In every 360 and PC mesh, each value
equals its field. The re-laid-out meshes kept the old values, so the loader
pointed the tables back at the old (shorter, zeroed) index data, and the
index buffer copy read past the end of the mesh (crash at exe+0x1044191).
The values are now refreshed from the converted fields.

## 36. Audio stream paths on PC

In the first playable test (drill tunnel as Gabe, intro terminal working)
subtitles showed but no dialogue played. Stream names come from SMB assets
(`pdlc1_vo_01_01.exa`). The exe (0x713190) opens `audiostreams\%s` +
`.exa.snu`, and the PC inserts a folder made of characters 4-11 of the
name (`audiostreams\1_vo_01_\pdlc1_vo_01_01.exa.snu`; the log showed the
loose-file attempt failing). The 360 keeps the streams flat. Checked against
the PC archives: 1,990 of the 2,045 base-game stream names (from the SMB
pairs) hash as `audiostreams\<name[4:12]>\<name>.exa.snu`. The other 55, all
names of 8 characters, sit flat in `audiostreams\`. Localised streams add the
language first (`audiostreams\fr\<name[4:12]>\<name>.exa.snu`, 979 hits).
`snu.pc_path` renames Severed's streams this way in the archive.

## 37. The intro hand-over (RIG call scene)

Console footage (1-3 min) shows the drill tunnel opening:
1. Gabe sits against the rock, helmet off.
2. The RIG call from the nurse plays on a video screen.
3. Gabe gets up, puts his helmet on, and play starts with the Pulse Rifle.

In our run Gabe stood, the camera stayed stuck and there was no weapon.

The chain, from the level SimGroups:
- **Start sequence.** `mm_pdlc1_ch01_initial_streamset` (MultiManager in
  the main SimGroup) sends, in order:
  - `opening_audio_and_vfx`
  - `equip_player_upgrade_nodes` (the neutralised Pulse Rifle class)
  - `push_cam_pole_initial` (0.1 s)
  - `equip_command_player_initial` (EquipCommand on the Player:
    8 items, all base-game item objects defined in
    `global_assets\global_assets.str`)
  - `mm_equip_tutorials_reverse_order`
  - `mm_sync_igc_01_01` (39 s)
- **RIG call scene.** `mm_sync_igc_01_01` (drill_tunnel_02):
  - starts `ses_player_01_01`, a ScriptedEventSequence on the Player with an
    action animation from `pdlc1_igc_01_01_player.bnk` and an audio file;
  - starts the video screen;
  - pops the pole camera and pushes `push_camera_01_01`.
- **Hand-over.** When the sequence ends it sends `ses_player_01_01_end`.
  That message:
  - pops that camera;
  - adds the objective;
  - sets the post-intro checkpoint, whose MultiManager equips
    `equip_command_player_initial` again;
  - plays the follow-up audio log.

The sequence starts its action when its audio is primed. With the audio
streams missing (section 36) it never started (Gabe never got up) and never
ended, so the camera and control were never handed back.

Messages are broadcast by name through exe 0x84F5A0 (cdecl: name, unused,
payload; behind Lua's SendMessage). Probe 19 sends the hand-over on F8.

## 38. 6-channel cutscene audio; first gameplay run

With the audio at its PC paths, the terminal dialogue played. Gabe's get-up
scene still never started. The probe showed its stream
(`pdlc1_igc_01_01`) being primed (the first ~780 KB read) but never played.

The stream has 6 channels (5.1). Of the base game's PC streams (archive
scan, SNR header):
- XAS (codec 4): 1, 2, 4 or 8 channels only;
- EALayer3 (codec 7): all 77 of the 6-channel streams.

Our 6-channel XAS stream evidently never reports "primed", so the scripted
sequence waiting on it never starts. 27 Severed streams are 6-channel: the
main cutscenes of both chapters and their translations.
- `snu.pad_channels` now writes them with 8 channels, the last two silent.
  Decoded back, the first six channels are identical.
- The SNU container's byte 3 is the channel count, and is set to match.

F8 (probe 20) worked as the fallback:
- `ses_player_01_01_end` popped the camera, added the objective and
  started the next dialogue;
- the player could walk the drill tunnel.

Health: the intro's HealthComponentTuningRelay sets Gabe to 50 health on
purpose.

The next crash was on picking up the Flamethrower. The base Flamethrower
weapon stream (DS2DAT9) loaded, then the `grinder_room` section, then the
game crashed in the CPU skinning job: exe 0x7C2CB0 locks a vertex buffer
through a garbage handle (exe+0xFD284E). Probe 21 now names the meshes
reachable from the crash registers.

## 39. Using the PC game's own copies of reused assets

The next crash (probe 21 named the meshes) was drawing
`kiosk_public01_am`, the base game's store / save kiosk, with the skinning
job locking a vertex buffer through a garbage handle.

The PC version of that mesh was exported with another vertex layout, not
just byte-swapped:
- DT1 +0x27 (bytes per vertex of the table's second stream) is 0x14 on PC,
  against 0x08 / 0x0C on the 360;
- the DT1 +7 flags byte is 00 on PC, where the 360 has 06 / 02;
- the MeshVolatile is 119,808 bytes on PC, against 54,400 converted.

This holds for about 10% of the base game's triangle-list tables (the
"re-exported" pairs of section 20).

Severed reuses many base-game assets. 13,256 of its assets have the same
type, name and ids as a PC asset, the key that pairs the base game's PC and
360 files. They are in 379 PC streams (DS2DAT6-9) and include:
- 850 meshes and 671 MeshVolatiles;
- 4,243 textures;
- materials, VFX, MetaModels, Havok files, animation banks;
- Gabe's RIG health bar meshes and materials.

The test script now takes these from the user's own PC archives:
- `ds2/pcassets.py`;
- the index `ds2/pc_assets.json` (names and entry hashes only), built by
  `learn_pc_assets.py` from the asset listings;
- meshes are taken with their MeshVolatile, and texture headers with their
  data, together or not at all.

The PC streams' RefPack chunks are now decoded natively (`native/refpack.c`,
in the same library as the XAS encoder). The Python decoder remains as a
fallback.

The RIG health display ("not there at all") likely has the same cause as the
kiosk.

Follow-up to section 38: the 8-channel version did not start the scene
either. The probe again showed only the prime reads.

The scene's settings decode against the engine's own enum names:
- MoveType 0 = RWS_MOVETYPE_NONE;
- PrimeType 0 = SES_PRIMETYPE_BEFORE;
- flags 0x4827 = REPEATABLE | NO_INTERRUPT | NO_GRAVITY_COLLISION |
  NO_DAMAGE | NO_CAMERA_RESET_WHEN_DONE | 0x4000.

So the action starts as soon as the audio is primed. 5.1 streams are now
mixed down to stereo, the layout of every stream that has played so far.

Severed's 5.1 channel order, from channel energy: L, C (the dialogue, the
loudest), R, Ls, Rs, LFE (silent). Mix:
- L' = L + 0.707 C + 0.707 Ls
- R' = R + 0.707 C + 0.707 Rs
- scaled down only if it would clip.

Working list of in-game progress: docs/PROGRESS.md.

## 40. The Player object resolved to a copy

The scripted sequence trace (probe 22) hooks the handler dispatcher of
ScriptedSequenceSM (exe 0xECA440). It recorded one state machine, in the
front end, and none at all in Severed. So `ses_player_01_01` never created
its state machine; its audio was primed, the first step on triggering.

Three things target the same Player object
`{52CB2210-69DE-25A9-5254-4E4F504C4145}`:
- the scene `ses_player_01_01`;
- `equip_command_player_initial`, even when sent by F8 (inventory empty);
- `set_health_player_health_initial`. The missing RIG health turned out to
  be the RIG bar meshes: it works since the PC game's own assets are used.
  Whether the health message itself arrives is not known.

Probe 12's experiment loaded a copy of the level SimGroup as
`pdlc1_ch01_mng_streamsets.str` in stream-sets mode, so every object of the
main SimGroup, the Player included, existed twice under one GUID.

Probe 23 no longer requests the copy. A file `severed_streamsets.on` in the
game folder brings it back, in case the level needs it after all: since the
Severed-only classes are neutralised, sections stream without it as far as
we know.

## 41. NAV blob checksums (AI running in place)

Necromorphs attacked but ran in place. The NAV loader (handler 0x1363220,
load callback 0x1363860) passes each blob of a collection to 0x5BBC30,
which adds it to the nav world through 0x5BB980. That function reads the
blob's 0x18-byte header (u32 endian marker, version 2, size, sum, flags)
and drops the blob, adding nothing, when:
- the version is not 2;
- flag bit 0 is set;
- the sum of the `size` bytes after the header, read as big-endian 32-bit
  words (0x5BADE0), differs from the header's sum.

The PC sum is over the little-endian converted bytes, so the 360 value never
matched: every Severed blob was dropped and the AI had no navigation. (The
earlier hash search tried CRC, Adler, FNV, sdbm and djb2, never a plain
word sum.) The sums verify on all 177 PC and 181 360 headers sampled.
`nav.checksums` recomputes them, innermost header first. All 770 pairs now
convert byte-exact, and all 96 Severed headers are found. The test build
re-converts the NAV assets once (`nav_sums.ok`).
