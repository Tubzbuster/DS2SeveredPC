<#
.SYNOPSIS
    Builds a text-only fingerprint of a Dead Space 2 file tree (PC install,
    extracted Severed DLC, or extracted Xbox 360 base game) so the formats can
    be analysed without uploading the game files themselves.

.DESCRIPTION
    Walks every file under -Path and writes, into scans\<Label>\:

      manifest.csv     one row per file: relative path, size, SHA-256, magic,
                       format guess and the first bytes as hex
      summary.txt      totals, per-extension and per-format breakdown
      samples.txt      a longer hex dump of a few files of every extension
      packages.txt     decoded header of any Xbox 360 STFS package (CON/LIVE/PIRS)
      executables.txt  PE (.exe/.dll) and XEX details, plus content/DLC-related
                       strings found inside them

    No game data is copied; only metadata and short header excerpts. Paths are
    stored relative to -Path so your Windows user name does not end up in the
    output.

    Works with the Windows PowerShell 5.1 that ships with Windows 10/11 and
    with PowerShell 7.

.PARAMETER Path
    Folder to scan, e.g. "C:\Program Files (x86)\Steam\steamapps\common\Dead Space 2".

.PARAMETER Label
    Short name for this scan. Suggested: PC, Severed360, Base360.

.PARAMETER OutDir
    Where the scan folder is created. Defaults to the repo's scans\ folder.

.PARAMETER SkipHash
    Skip the SHA-256 of every file (much faster on big installs).

.EXAMPLE
    .\Scan-DS2Files.ps1 -Path "D:\Games\Dead Space 2" -Label PC
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Label,
    [string]$OutDir,
    [switch]$SkipHash,
    [int]$HeaderBytes = 64,
    [int]$SamplesPerExt = 3,
    [int]$SampleBytes = 512
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

function Read-Head([string]$file, [int]$count) {
    $fs = [System.IO.File]::Open($file, 'Open', 'Read', 'ReadWrite')
    try {
        $len = [int][Math]::Min([int64]$count, $fs.Length)
        $buf = New-Object byte[] $len
        $read = 0
        while ($read -lt $len) {
            $n = $fs.Read($buf, $read, $len - $read)
            if ($n -le 0) { break }
            $read += $n
        }
        return , $buf
    } finally { $fs.Dispose() }
}

function To-Hex([byte[]]$bytes, [int]$count) {
    $n = [Math]::Min($count, $bytes.Length)
    if ($n -le 0) { return '' }
    return ([System.BitConverter]::ToString($bytes, 0, $n)).Replace('-', ' ')
}

function To-Ascii([byte[]]$bytes, [int]$offset, [int]$count) {
    $sb = New-Object System.Text.StringBuilder
    $end = [Math]::Min($bytes.Length, $offset + $count)
    for ($i = $offset; $i -lt $end; $i++) {
        $b = $bytes[$i]
        if ($b -ge 0x20 -and $b -le 0x7E) { [void]$sb.Append([char]$b) } else { [void]$sb.Append('.') }
    }
    return $sb.ToString()
}

function Hex-Dump([byte[]]$bytes) {
    $lines = New-Object System.Collections.Generic.List[string]
    for ($o = 0; $o -lt $bytes.Length; $o += 16) {
        $n = [Math]::Min(16, $bytes.Length - $o)
        $hex = ([System.BitConverter]::ToString($bytes, $o, $n)).Replace('-', ' ')
        $lines.Add(('{0:X8}  {1,-47}  {2}' -f $o, $hex, (To-Ascii $bytes $o $n)))
    }
    return $lines
}

function U32BE([byte[]]$b, [int]$o) {
    if ($o + 4 -gt $b.Length) { return $null }
    return ([uint32]$b[$o] -shl 24) -bor ([uint32]$b[$o + 1] -shl 16) -bor ([uint32]$b[$o + 2] -shl 8) -bor [uint32]$b[$o + 3]
}

function U16LE([byte[]]$b, [int]$o) { return [System.BitConverter]::ToUInt16($b, $o) }
function U32LE([byte[]]$b, [int]$o) { return [System.BitConverter]::ToUInt32($b, $o) }

function Utf16BE([byte[]]$b, [int]$o, [int]$len) {
    if ($o + $len -gt $b.Length) { return '' }
    $s = [System.Text.Encoding]::BigEndianUnicode.GetString($b, $o, $len)
    return ($s -split [char]0)[0]
}

function Magic-Text([byte[]]$b) {
    if ($b.Length -lt 4) { return (To-Ascii $b 0 $b.Length) }
    return (To-Ascii $b 0 4)
}

function Guess-Format([byte[]]$b) {
    if ($b.Length -eq 0) { return 'empty' }
    $m4 = if ($b.Length -ge 4) { [System.Text.Encoding]::ASCII.GetString($b, 0, 4) } else { '' }
    switch -CaseSensitive ($m4) {
        'CON ' { return 'X360 STFS package (CON)' }
        'LIVE' { return 'X360 STFS package (LIVE)' }
        'PIRS' { return 'X360 STFS package (PIRS)' }
        'XEX2' { return 'X360 executable (XEX2)' }
        'XEX1' { return 'X360 executable (XEX1)' }
        'DDS ' { return 'DDS texture' }
        'BIGF' { return 'EA BIG archive (BIGF)' }
        'BIG4' { return 'EA BIG archive (BIG4)' }
        'BIGH' { return 'EA BIG archive (BIGH)' }
        'SCHl' { return 'EA audio stream (SCHl)' }
        'OggS' { return 'Ogg' }
        'FSB4' { return 'FMOD sound bank (FSB4)' }
        'FSB5' { return 'FMOD sound bank (FSB5)' }
        'BKHD' { return 'Wwise sound bank' }
        'AKPK' { return 'Wwise package' }
        'DXBC' { return 'DirectX shader bytecode' }
        'RIFX' { return 'RIFF big-endian (RIFX)' }
    }
    if ($m4 -ceq 'RIFF' -and $b.Length -ge 12) {
        return ('RIFF/' + [System.Text.Encoding]::ASCII.GetString($b, 8, 4))
    }
    if ($b.Length -ge 3) {
        $m3 = [System.Text.Encoding]::ASCII.GetString($b, 0, 3)
        if ($m3 -ceq 'BIK' -or $m3 -ceq 'KB2') { return 'Bink video' }
    }
    if ($b.Length -ge 2 -and $b[0] -eq 0x4D -and $b[1] -eq 0x5A) { return 'PE/MZ executable' }
    if ($b.Length -ge 4 -and $b[0] -eq 0x50 -and $b[1] -eq 0x4B -and $b[2] -eq 3 -and $b[3] -eq 4) { return 'ZIP' }
    if ($b.Length -ge 2 -and $b[0] -eq 0x1F -and $b[1] -eq 0x8B) { return 'gzip' }
    if ($b.Length -ge 2 -and $b[0] -eq 0x78 -and ($b[1] -eq 0x01 -or $b[1] -eq 0x5E -or $b[1] -eq 0x9C -or $b[1] -eq 0xDA)) { return 'zlib stream?' }
    if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) { return 'text (UTF-16LE BOM)' }
    if ($b.Length -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) { return 'text (UTF-16BE BOM)' }
    if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) { return 'text (UTF-8 BOM)' }
    $printable = 0
    foreach ($x in $b) { if (($x -ge 0x20 -and $x -le 0x7E) -or $x -eq 9 -or $x -eq 10 -or $x -eq 13) { $printable++ } }
    if ($printable -eq $b.Length) {
        if ($m4 -ceq '<?xm') { return 'XML' }
        return 'text'
    }
    $zeros = 0
    foreach ($x in $b) { if ($x -eq 0) { $zeros++ } }
    if ($zeros -eq $b.Length) { return 'unknown (starts with zeros)' }
    return 'unknown'
}

function Describe-Stfs([string]$file, [string]$rel) {
    $b = Read-Head $file 0x1800
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("== $rel")
    $lines.Add(('Magic           : {0}' -f (Magic-Text $b)))
    if ($b.Length -lt 0x420) { $lines.Add('(file too short for a full STFS header)'); return $lines }
    $ctype = U32BE $b 0x344
    $ctypeName = switch ($ctype) {
        0x00000001 { 'Saved game' }
        0x00000002 { 'Marketplace content (DLC)' }
        0x00000003 { 'Publisher' }
        0x00007000 { 'Games on Demand' }
        0x000D0000 { 'Arcade title' }
        0x000B0000 { 'Installed game / title update' }
        0x00080000 { 'Game demo' }
        0x00090000 { 'Video' }
        0x00100000 { 'Profile' }
        default { 'other' }
    }
    $lines.Add(('Content type    : 0x{0:X8} ({1})' -f $ctype, $ctypeName))
    $lines.Add(('Metadata version: {0}' -f (U32BE $b 0x348)))
    $lines.Add(('Media ID        : 0x{0:X8}' -f (U32BE $b 0x354)))
    $lines.Add(('Version         : 0x{0:X8}' -f (U32BE $b 0x358)))
    $lines.Add(('Base version    : 0x{0:X8}' -f (U32BE $b 0x35C)))
    $lines.Add(('Title ID        : 0x{0:X8}' -f (U32BE $b 0x360)))
    $lines.Add(('Disc            : {0} of {1}' -f $b[0x366], $b[0x367]))
    $lines.Add(('Display name    : {0}' -f (Utf16BE $b 0x411 0x80)))
    if ($b.Length -ge 0x1711) { $lines.Add(('Title name      : {0}' -f (Utf16BE $b 0x1691 0x80))) }
    $lines.Add('First 0x40 bytes of the metadata block (0x22C):')
    $meta = New-Object byte[] 0x40
    [Array]::Copy($b, 0x22C, $meta, 0, 0x40)
    foreach ($l in (Hex-Dump $meta)) { $lines.Add('  ' + $l) }
    return $lines
}

$keywordPattern = 'dlc|sever|weller|lexine|titan|download|marketplace|entitle|content|package|mount|chapter|\.str\b|\.viv\b|\.big\b|\.toc\b|\.sb\b|\.arc\b|\.ini\b|\.cfg\b'

function Describe-Executable([string]$file, [string]$rel, [string]$kind) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("== $rel  [$kind]")
    $all = [System.IO.File]::ReadAllBytes($file)
    if ($kind -eq 'PE') {
        try {
            $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($file)
            $lines.Add(('Product         : {0} {1}' -f $vi.ProductName, $vi.ProductVersion))
            $lines.Add(('File version    : {0}' -f $vi.FileVersion))
            $lines.Add(('Company         : {0}' -f $vi.CompanyName))
            $lines.Add(('Original name   : {0}' -f $vi.OriginalFilename))
        } catch { $lines.Add('Version info    : (unreadable)') }
        if ($all.Length -ge 0x40) {
            $peOff = [int](U32LE $all 0x3C)
            if ($peOff -gt 0 -and $peOff + 24 -le $all.Length -and $all[$peOff] -eq 0x50 -and $all[$peOff + 1] -eq 0x45) {
                $machine = U16LE $all ($peOff + 4)
                $nsec = U16LE $all ($peOff + 6)
                $stamp = U32LE $all ($peOff + 8)
                $optSize = U16LE $all ($peOff + 20)
                $chars = U16LE $all ($peOff + 22)
                $machineName = switch ($machine) { 0x14C { 'x86 (32-bit)' } 0x8664 { 'x64' } default { 'other' } }
                $lines.Add(('Machine         : 0x{0:X4} {1}' -f $machine, $machineName))
                $lines.Add(('Link timestamp  : {0:yyyy-MM-dd HH:mm:ss} UTC' -f ([DateTime]'1970-01-01').AddSeconds($stamp)))
                $lines.Add(('Characteristics : 0x{0:X4}{1}' -f $chars, $(if ($chars -band 0x2000) { ' (DLL)' } else { '' })))
                $secOff = $peOff + 24 + $optSize
                $lines.Add('Sections        :')
                for ($i = 0; $i -lt $nsec; $i++) {
                    $s = $secOff + 40 * $i
                    if ($s + 40 -gt $all.Length) { break }
                    $name = ([System.Text.Encoding]::ASCII.GetString($all, $s, 8)).TrimEnd([char]0)
                    $lines.Add(('  {0,-8} vsize=0x{1:X8} rva=0x{2:X8} rawsize=0x{3:X8} flags=0x{4:X8}' -f `
                                $name, (U32LE $all ($s + 8)), (U32LE $all ($s + 12)), (U32LE $all ($s + 16)), (U32LE $all ($s + 36))))
                }
            } else { $lines.Add('(no valid PE header)') }
        }
    } else {
        $lines.Add('(XEX files are normally compressed/encrypted, so few strings are expected)')
        if ($all.Length -ge 24) {
            $lines.Add(('Module flags    : 0x{0:X8}' -f (U32BE $all 4)))
            $lines.Add(('PE data offset  : 0x{0:X8}' -f (U32BE $all 8)))
            $lines.Add(('Header count    : {0}' -f (U32BE $all 20)))
        }
    }

    # Strings that look relevant to content loading / DLC / menus.
    $latin = [System.Text.Encoding]::GetEncoding(28591).GetString($all)
    $hits = New-Object System.Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($latin, '[\x20-\x7E]{5,}')) {
        if ($m.Value -match $keywordPattern) { $hits.Add(('  0x{0:X8} A  {1}' -f $m.Index, $m.Value)) }
    }
    foreach ($m in [regex]::Matches($latin, '(?:[\x20-\x7E]\x00){5,}')) {
        $v = $m.Value.Replace([string][char]0, '')
        if ($v -match $keywordPattern) { $hits.Add(('  0x{0:X8} W  {1}' -f $m.Index, $v)) }
    }
    $lines.Add(('Relevant strings: {0} (A = ASCII, W = UTF-16)' -f $hits.Count))
    $limit = 3000
    $i = 0
    foreach ($h in $hits) {
        if ($i -ge $limit) { $lines.Add("  ... truncated after $limit"); break }
        $lines.Add($h); $i++
    }
    return $lines
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

$root = (Resolve-Path -LiteralPath $Path).ProviderPath.TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Not a folder: $Path" }

if (-not $OutDir) { $OutDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'scans' }
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]', '_')
$dest = Join-Path $OutDir $safeLabel
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "Scanning $root"
Write-Host "Writing to $dest"

$files = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue | Sort-Object FullName)
$total = $files.Count
Write-Host "$total files found"

$rows = New-Object System.Collections.Generic.List[object]
$stfs = New-Object System.Collections.Generic.List[object]
$exes = New-Object System.Collections.Generic.List[object]
$errors = New-Object System.Collections.Generic.List[string]
$sw = [System.Diagnostics.Stopwatch]::StartNew()

for ($idx = 0; $idx -lt $total; $idx++) {
    $f = $files[$idx]
    $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/')
    if (($idx % 25) -eq 0) {
        Write-Progress -Activity "Scanning $safeLabel" -Status "$idx / $total  $rel" -PercentComplete ([int](100 * $idx / [Math]::Max(1, $total)))
    }
    try {
        $head = Read-Head $f.FullName ([Math]::Max($HeaderBytes, 64))
        $fmt = Guess-Format $head
        $hash = ''
        if (-not $SkipHash) { $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash }
        $rows.Add([pscustomobject]@{
            RelativePath = $rel
            Extension    = $f.Extension.ToLowerInvariant()
            Size         = $f.Length
            SHA256       = $hash
            Magic        = (Magic-Text $head)
            Format       = $fmt
            HeaderHex    = (To-Hex $head $HeaderBytes)
        })
        if ($fmt -like 'X360 STFS*') { $stfs.Add([pscustomobject]@{ Full = $f.FullName; Rel = $rel }) }
        elseif ($fmt -eq 'PE/MZ executable') { $exes.Add([pscustomobject]@{ Full = $f.FullName; Rel = $rel; Kind = 'PE' }) }
        elseif ($fmt -like 'X360 executable*') { $exes.Add([pscustomobject]@{ Full = $f.FullName; Rel = $rel; Kind = 'XEX' }) }
    } catch {
        $errors.Add("$rel : $($_.Exception.Message)")
    }
}
Write-Progress -Activity "Scanning $safeLabel" -Completed

# manifest.csv
$rows | Export-Csv -LiteralPath (Join-Path $dest 'manifest.csv') -NoTypeInformation -Encoding UTF8

# summary.txt
$sum = New-Object System.Collections.Generic.List[string]
$totalBytes = [int64]0
foreach ($r in $rows) { $totalBytes += $r.Size }
$sum.Add("DS2 file scan: $safeLabel")
$sum.Add(('Scanned folder : {0}' -f (Split-Path $root -Leaf)))
$sum.Add(('Scan date      : {0:yyyy-MM-dd HH:mm} (local)' -f (Get-Date)))
$sum.Add(('PowerShell     : {0}' -f $PSVersionTable.PSVersion))
$sum.Add(('Files          : {0}' -f $rows.Count))
$sum.Add(('Total size     : {0:N0} bytes ({1:N2} GB)' -f $totalBytes, ($totalBytes / 1GB)))
$sum.Add(('Hashes         : {0}' -f $(if ($SkipHash) { 'skipped' } else { 'SHA-256' })))
$sum.Add(('Elapsed        : {0:N0} s' -f $sw.Elapsed.TotalSeconds))
$sum.Add('')
$sum.Add('Top-level folders:')
foreach ($g in ($rows | Group-Object { ($_.RelativePath -split '[\\/]')[0] } | Sort-Object Name)) {
    $sz = ($g.Group | Measure-Object Size -Sum).Sum
    $sum.Add(('  {0,-40} {1,8} files {2,18:N0} bytes' -f $g.Name, $g.Count, $sz))
}
$sum.Add('')
$sum.Add('By extension:')
foreach ($g in ($rows | Group-Object Extension | Sort-Object Count -Descending)) {
    $sz = ($g.Group | Measure-Object Size -Sum).Sum
    $name = if ($g.Name) { $g.Name } else { '(none)' }
    $magics = ($g.Group | Group-Object Magic | Sort-Object Count -Descending | Select-Object -First 3 | ForEach-Object { "'$($_.Name)' x$($_.Count)" }) -join ', '
    $sum.Add(('  {0,-12} {1,8} files {2,18:N0} bytes   magic: {3}' -f $name, $g.Count, $sz, $magics))
}
$sum.Add('')
$sum.Add('By detected format:')
foreach ($g in ($rows | Group-Object Format | Sort-Object Count -Descending)) {
    $sum.Add(('  {0,-34} {1,8} files' -f $g.Name, $g.Count))
}
if ($errors.Count -gt 0) {
    $sum.Add('')
    $sum.Add("Unreadable files ($($errors.Count)):")
    foreach ($e in $errors) { $sum.Add('  ' + $e) }
}
$sum | Set-Content -LiteralPath (Join-Path $dest 'summary.txt') -Encoding UTF8

# samples.txt: smallest and largest files of each extension
$smp = New-Object System.Collections.Generic.List[string]
$smp.Add("Header samples ($SampleBytes bytes) - $safeLabel")
foreach ($g in ($rows | Group-Object Extension | Sort-Object Name)) {
    $sorted = @($g.Group | Sort-Object Size)
    $pick = New-Object System.Collections.Generic.List[object]
    foreach ($r in ($sorted | Select-Object -First ([Math]::Max(1, $SamplesPerExt - 1)))) { $pick.Add($r) }
    $largest = $sorted[$sorted.Count - 1]
    if (-not $pick.Contains($largest)) { $pick.Add($largest) }
    foreach ($r in $pick) {
        $smp.Add('')
        $smp.Add(('== {0}  ({1:N0} bytes, {2})' -f $r.RelativePath, $r.Size, $r.Format))
        try {
            $b = Read-Head (Join-Path $root $r.RelativePath) $SampleBytes
            foreach ($l in (Hex-Dump $b)) { $smp.Add($l) }
        } catch { $smp.Add("  (unreadable: $($_.Exception.Message))") }
    }
}
$smp | Set-Content -LiteralPath (Join-Path $dest 'samples.txt') -Encoding UTF8

# packages.txt
$pkg = New-Object System.Collections.Generic.List[string]
$pkg.Add("Xbox 360 STFS packages - $safeLabel ($($stfs.Count) found)")
foreach ($p in $stfs) {
    $pkg.Add('')
    try { foreach ($l in (Describe-Stfs $p.Full $p.Rel)) { $pkg.Add($l) } }
    catch { $pkg.Add("== $($p.Rel)  (error: $($_.Exception.Message))") }
}
$pkg | Set-Content -LiteralPath (Join-Path $dest 'packages.txt') -Encoding UTF8

# executables.txt
$exe = New-Object System.Collections.Generic.List[string]
$exe.Add("Executables - $safeLabel ($($exes.Count) found)")
$exe.Add("String filter: $keywordPattern")
foreach ($x in $exes) {
    $exe.Add('')
    Write-Host "Inspecting $($x.Rel)"
    try { foreach ($l in (Describe-Executable $x.Full $x.Rel $x.Kind)) { $exe.Add($l) } }
    catch { $exe.Add("== $($x.Rel)  (error: $($_.Exception.Message))") }
}
$exe | Set-Content -LiteralPath (Join-Path $dest 'executables.txt') -Encoding UTF8

Write-Host ''
Write-Host "Done in $([int]$sw.Elapsed.TotalSeconds) s. $($rows.Count) files, $($stfs.Count) STFS packages, $($exes.Count) executables."
Write-Host "Results: $dest"
if ($errors.Count -gt 0) { Write-Warning "$($errors.Count) files could not be read; see summary.txt" }
