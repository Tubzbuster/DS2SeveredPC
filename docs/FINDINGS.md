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
