# DS2SeveredPC

Goal: make the Xbox 360 *Dead Space 2: Severed* DLC launchable from the PC
version of Dead Space 2, the way it is on console.

Step 1 is working out how the PC and Xbox 360 file formats differ. The
scanner in `tools/scan/` produces text-only reports for that. **No game
files go into this repo**, only the scan output.

## Running the scanner (Windows)

1. Double-click `tools\scan\Scan-DS2Files.bat`, or drag a folder onto it.
2. Enter the folder to scan, a label, and whether to also extract Xbox 360
   package contents (answer `y` only if you want the raw files; they go to
   `tools\scan\extracted\`, which git ignores). When it finishes, the
   results are in `tools\scan\scans\<Label>\`, next to the scripts.

Or from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\scan\Scan-DS2Files.ps1 -Path "D:\Games\Dead Space 2" -Label PC
```

Add `-SkipHash` if hashing a large install is too slow, and
`-ExtractTo <folder>` to extract package contents.

## What to scan

| Label        | Folder                                                                 |
|--------------|------------------------------------------------------------------------|
| `PC`         | The PC install folder (the one containing the game `.exe`)             |
| `Severed360` | A folder holding just the Severed DLC package file                     |
| `Base360`    | (optional, very useful) the extracted Xbox 360 base game, including `default.xex` |

The Severed DLC comes as a single Xbox 360 package file with a long hex name
(e.g. `29E2FCC04BEF1D2532C48269EC42EF2E3DBFC45845`). Put it in a folder on its
own and scan that folder. The scanner reads the package directly: its header,
its full file listing, and a fingerprint of every file inside it (listed in
the manifest as `<package>::<path inside package>`). No extracting needed.

## Output (`tools\scan\scans\<Label>\`)

| File              | Contents                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `summary.txt`     | Totals, per-folder, per-extension and per-format breakdown               |
| `manifest.csv`    | Every file: relative path, size, SHA-256, magic bytes, format guess, first 64 bytes as hex |
| `samples.txt`     | 512-byte hex dumps of the smallest and largest file of each extension    |
| `packages.txt`    | Decoded Xbox 360 package headers (content type, title ID, name) and the full list of files inside |
| `executables.txt` | EXE/DLL/XEX details (version, sections) and DLC/content-related strings  |

Paths are stored relative to the scanned folder, so your Windows user name
does not appear in the output. Commit the `tools/scan/scans/` folder and push.
