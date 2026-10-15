# DS2SeveredPC

Goal: make the Xbox 360 *Dead Space 2: Severed* DLC launchable from the PC
version of Dead Space 2, the way it is on console.

Step 1 is working out how the PC and Xbox 360 file formats differ. The
scanner in `tools/scan/` produces text-only reports for that. **No game
files go into this repo**, only the scan output.

## Running the scanner (Windows)

1. Double-click `tools\scan\Scan-DS2Files.bat`, or drag a folder onto it.
2. Enter the folder to scan and a label. When it finishes, the results are in
   `scans\<Label>\`.

Or from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\scan\Scan-DS2Files.ps1 -Path "D:\Games\Dead Space 2" -Label PC
```

Add `-SkipHash` if hashing a large install is too slow.

## What to scan

| Label        | Folder                                                                 |
|--------------|------------------------------------------------------------------------|
| `PC`         | The PC install folder (the one containing the game `.exe`)             |
| `Severed360` | A folder holding the **raw** DLC package *and* its extracted contents  |
| `Base360`    | (optional, very useful) the extracted Xbox 360 base game, including `default.xex` |

For `Severed360`, put the unextracted package file (the one with a long hex
name, starting with `LIVE`) in the folder alongside the extracted files, so
its header gets decoded too.

## Output (`scans\<Label>\`)

| File              | Contents                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `summary.txt`     | Totals, per-folder, per-extension and per-format breakdown               |
| `manifest.csv`    | Every file: relative path, size, SHA-256, magic bytes, format guess, first 64 bytes as hex |
| `samples.txt`     | 512-byte hex dumps of the smallest and largest file of each extension    |
| `packages.txt`    | Decoded Xbox 360 STFS package headers (content type, title ID, name)     |
| `executables.txt` | EXE/DLL/XEX details (version, sections) and DLC/content-related strings  |

Paths are stored relative to the scanned folder, so your Windows user name
does not appear in the output. Commit the `scans/` folder and push.
