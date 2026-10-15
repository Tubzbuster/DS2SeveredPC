# Design (draft)

Status: **provisional**. See [FINDINGS.md](FINDINGS.md) for what the first scans showed; section 6 there supersedes the open questions below where they overlap.

 Nothing below is decided until the scans of the PC
install, the Severed package and the Xbox 360 base game have been analysed.
Each open question lists what will answer it.

## Goal

Someone who owns the PC game and the Xbox 360 Severed DLC can:

1. Run a small installer app.
2. Point it at their Severed package file (the `29E2FC…845`-style file).
3. Get the DLC installed into their PC Dead Space 2 folder.
4. Launch the normal PC exe and pick **Severed** from the main menu, as on
   console.

The mod only ships our own code. Every game asset comes from the user's own
copy of the DLC, converted on their machine.

## Planned pieces

```
 Severed package (user's file)
        │
        ▼
 ┌──────────────────────┐   1. Read package (STFS reader already in tools/scan)
 │ Installer app        │   2. Convert each asset 360 → PC format
 │ (Windows, one window)│   3. Write into <DS2>\Severed\ (or wherever the PC
 └──────────────────────┘      layout requires)
        │                   4. Drop loader DLL into the game folder
        ▼
 ┌──────────────────────┐   - Loaded by the game via a proxy DLL
 │ Loader DLL           │   - Makes the engine find the Severed content
 │ (hooks deadspace2.exe│   - Adds the Severed main-menu entry and starts
 │  in memory)          │     the DLC chapters
 └──────────────────────┘
```

Hooking in memory from a DLL is preferred over patching the exe on disk: the
original exe stays intact, game updates or Steam file checks don't undo it,
and uninstalling is just deleting files.

### 1. Package reader
Done in principle: `tools/scan/Scan-DS2Files.ps1` already lists and extracts
STFS packages. The installer will port that logic to its own language.

### 2. Asset converter
The largest part. Expected work, to be confirmed by the scans:

| Asset kind        | Likely 360 → PC work                                        |
|-------------------|-------------------------------------------------------------|
| Containers/levels | Byte-order swap of headers and tables; rebuild offsets      |
| Textures          | Untile Xbox 360 texture memory layout, write PC DDS         |
| Models/animations | Byte-order swap; vertex formats may differ                  |
| Shaders           | Can't convert; use the PC game's equivalents                |
| Audio             | XMA → PC format the engine accepts                          |
| Video             | Bink is cross-platform, may copy as-is                      |
| Scripts/tables    | Byte-order swap; check for 360-only references              |

The base-game 360 files are what make this tractable: the same asset in both
the 360 and the PC build shows exactly how each format differs, and the
converter can be tested by converting a 360 base-game file and comparing it
with the PC original.

### 3. Loader DLL
Needs reverse engineering of the PC exe (and the 360 `default.xex` for
reference) to find:
- how the game mounts content and resolves file paths
- whether the PC exe still contains DLC/content-package code from the console
  build, unused (if so, the hook may just switch it on)
- how the main menu is built and how a chapter/level is launched

### 4. Installer app
Small Windows app: pick the package, detect the game folder (Steam / EA app
registry keys, or browse), check the package's title ID and file hashes
against known good values, convert, install, and uninstall.

## Open questions

| Question | Answered by |
|----------|-------------|
| Which PC archive/level formats exist, and are they the same family as 360? | `PC` and `Base360` scans |
| Does Severed ship whole new archives, or patches to base ones? | `Severed360` scan (packages.txt) |
| Which Severed files have byte-identical PC equivalents (copy as-is)? | Hash comparison across scans |
| Does the PC exe contain leftover DLC/content code? | `executables.txt` of the PC scan, then disassembly |
| Is the PC exe protected/packed (Steam DRM, EA/Origin wrapper)? | Section names in `executables.txt` |
| Exact install location (`<DS2>\Severed\` or merged into base folders)? | How the exe resolves paths |

## Getting the Xbox 360 base game files

From the disc image, extract the files (e.g. with extract-xiso) and scan the
resulting folder with label `Base360`. `default.xex` is normally encrypted and
compressed; a decrypted copy (e.g. `xextool -b default.exe default.xex`)
would help later reverse engineering but is not needed for the first scan.
