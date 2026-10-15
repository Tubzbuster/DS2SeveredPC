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
