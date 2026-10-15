<#
.SYNOPSIS
    Builds a test archive DS2DAT<n>.DAT in the Dead Space 2 folder containing
    unmodified copies of a few of the game's own files, or removes it.

.DESCRIPTION
    The game opens DS2DAT0.DAT ... DS2DAT12.DAT at startup, whichever exist.
    This writes a new one (default DS2DAT2.DAT) in the same BIGH format,
    holding byte-identical copies of files already in the other archives.
    With the probe DLL installed, the log then shows whether the game reads
    those files from the new archive or from the originals, which tells us
    whether an added archive can override base-game files (Severed replaces
    global_assets\global_assets_global.str).

    Because the copies are identical, the game should behave exactly as
    normal either way. Remove it with -Remove.

    Never overwrites an archive it did not create: the test archive is marked
    by a "<name>.severedtest" file next to it.

.EXAMPLE
    .\New-TestArchive.ps1 -GameDir "J:\SteamLibrary\steamapps\common\Dead Space 2"
.EXAMPLE
    .\New-TestArchive.ps1 -GameDir "J:\...\Dead Space 2" -Remove
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [ValidateRange(0, 12)][int]$Slot = 2,
    [string[]]$Names = @(
        'frontend\frontend.toc',
        'frontend\frontend_global.toc',
        'frontend\frontend_global.str',
        'frontend\frontend.str',
        'global_assets\global_assets_global.toc',
        'global_assets\global_assets_global.str'
    ),
    [switch]$Remove
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

Write-Host 'New-TestArchive version 3'
$target = Join-Path $GameDir ("DS2DAT{0}.DAT" -f $Slot)
$marker = $target + '.severedtest'

if ($Remove) {
    if (-not (Test-Path -LiteralPath $target)) { Write-Host "Nothing to remove: $target does not exist."; return }
    if (-not (Test-Path -LiteralPath $marker)) { throw "$target was not created by this script (no $marker); not touching it." }
    Remove-Item -LiteralPath $target, $marker
    Write-Host "Removed $target"
    return
}

if ((Test-Path -LiteralPath $target) -and -not (Test-Path -LiteralPath $marker)) {
    throw "$target already exists and was not created by this script; not overwriting it."
}

function Get-NameHash([string]$name) {
    $h = [uint64]0
    foreach ($c in [System.Text.Encoding]::ASCII.GetBytes($name.ToLowerInvariant())) { $h = ($h * 65599 + $c) % 4294967296 }
    return [uint32]$h
}

function Read-Exact($fs, [int64]$offset, [int]$count) {
    $buf = New-Object byte[] $count
    $fs.Position = $offset
    $read = 0
    while ($read -lt $count) {
        $n = $fs.Read($buf, $read, $count - $read)
        if ($n -le 0) { throw 'Unexpected end of file' }
        $read += $n
    }
    return , $buf
}

function U32BE([byte[]]$b, [int]$o) {
    return ([uint32]$b[$o] -shl 24) -bor ([uint32]$b[$o + 1] -shl 16) -bor ([uint32]$b[$o + 2] -shl 8) -bor [uint32]$b[$o + 3]
}

function Put-U32BE([byte[]]$b, [int]$o, [uint32]$v) {
    $b[$o] = [byte](($v -shr 24) -band 0xFF); $b[$o + 1] = [byte](($v -shr 16) -band 0xFF)
    $b[$o + 2] = [byte](($v -shr 8) -band 0xFF); $b[$o + 3] = [byte]($v -band 0xFF)
}

# Index the existing archives (not the target slot).
$sources = @{}
$trailer = $null
foreach ($a in (Get-ChildItem -LiteralPath $GameDir -Filter 'DS2DAT*.DAT' -File | Where-Object { $_.FullName -ne $target } | Sort-Object Name)) {
    $fs = [System.IO.File]::Open($a.FullName, 'Open', 'Read', 'ReadWrite')
    try {
        $h = Read-Exact $fs 0 16
        if ([System.Text.Encoding]::ASCII.GetString($h, 0, 4) -ne 'BIGH') { continue }
        $count = [int](U32BE $h 8)
        $hsz = [int](U32BE $h 12)
        $dir = Read-Exact $fs 16 ($count * 12)
        if ($null -eq $trailer -and $hsz -gt 16 + $count * 12) { $trailer = Read-Exact $fs (16 + $count * 12) ($hsz - 16 - $count * 12) }
        for ($i = 0; $i -lt $count; $i++) {
            $hash = U32BE $dir ($i * 12 + 8)
            if (-not $sources.ContainsKey($hash)) {
                $sources[$hash] = @{ File = $a.FullName; Offset = [int64](U32BE $dir ($i * 12)); Size = [int64](U32BE $dir ($i * 12 + 4)) }
            }
        }
    } finally { $fs.Dispose() }
}
if ($sources.Count -eq 0) { throw "No DS2DAT*.DAT archives found in $GameDir" }
if ($null -eq $trailer) { $trailer = New-Object byte[] 8 }

$entries = New-Object System.Collections.Generic.List[object]
foreach ($n in $Names) {
    $hash = Get-NameHash $n
    if (-not $sources.ContainsKey($hash)) { Write-Warning ("{0} (#{1:X8}) not found in the game's archives; skipped" -f $n, $hash); continue }
    $src = $sources[$hash]
    $entries.Add([pscustomobject]@{ Name = $n; Hash = $hash; File = $src.File; SrcOffset = $src.Offset; Size = $src.Size; Offset = [int64]0 })
}
if ($entries.Count -eq 0) { throw 'No entries to write.' }
$entries = @($entries | Sort-Object Hash)

# Layout: header + table + trailer, then each entry at a 0x800-aligned offset.
$hsz = 16 + 12 * $entries.Count + $trailer.Length
$pos = [int64][Math]::Ceiling($hsz / 2048.0) * 2048
foreach ($e in $entries) { $e.Offset = $pos; $pos = [int64][Math]::Ceiling(($pos + $e.Size) / 2048.0) * 2048 }
$total = $pos
if ($total -gt [uint32]::MaxValue) { throw 'Archive would exceed 4 GB.' }

$head = New-Object byte[] $hsz
[System.Text.Encoding]::ASCII.GetBytes('BIGH').CopyTo($head, 0)
[System.BitConverter]::GetBytes([uint32]$total).CopyTo($head, 4)   # little-endian, as in the game's archives
Put-U32BE $head 8 ([uint32]$entries.Count)
Put-U32BE $head 12 ([uint32]$hsz)
for ($i = 0; $i -lt $entries.Count; $i++) {
    Put-U32BE $head (16 + $i * 12) ([uint32]$entries[$i].Offset)
    Put-U32BE $head (20 + $i * 12) ([uint32]$entries[$i].Size)
    Put-U32BE $head (24 + $i * 12) ([uint32]$entries[$i].Hash)
}
$trailer.CopyTo($head, 16 + 12 * $entries.Count)

$tmp = $target + '.tmp'
if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp }   # left over from a failed run
$out = [System.IO.File]::Create($tmp)
$written = $false
try {
    $out.Write($head, 0, $head.Length)
    $buf = New-Object byte[] 1048576
    foreach ($e in $entries) {
        $out.SetLength($e.Offset); $out.Position = $e.Offset
        $in = [System.IO.File]::Open($e.File, 'Open', 'Read', 'ReadWrite')
        try {
            $in.Position = $e.SrcOffset
            $left = $e.Size
            while ($left -gt 0) {
                $n = $in.Read($buf, 0, [int][Math]::Min($buf.Length, $left))
                if ($n -le 0) { throw 'short read' }
                $out.Write($buf, 0, $n)
                $left -= $n
            }
        } finally { $in.Dispose() }
    }
    $out.SetLength($total)
    $written = $true
} finally {
    $out.Dispose()
    if (-not $written) { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

# Verify every entry against its source before putting the archive in place,
# comparing the bytes directly (no hashing, so nothing version-specific).
function Test-SameRange([string]$fileA, [int64]$offA, [string]$fileB, [int64]$offB, [int64]$size) {
    $fa = [System.IO.File]::Open($fileA, 'Open', 'Read', 'ReadWrite')
    $fb = [System.IO.File]::Open($fileB, 'Open', 'Read', 'ReadWrite')
    try {
        $fa.Position = $offA
        $fb.Position = $offB
        $ba = New-Object byte[] 1048576
        $bb = New-Object byte[] 1048576
        $left = $size
        while ($left -gt 0) {
            $want = [int][Math]::Min($ba.Length, $left)
            $na = 0; while ($na -lt $want) { $r = $fa.Read($ba, $na, $want - $na); if ($r -le 0) { return $false }; $na += $r }
            $nb = 0; while ($nb -lt $want) { $r = $fb.Read($bb, $nb, $want - $nb); if ($r -le 0) { return $false }; $nb += $r }
            if ([System.Convert]::ToBase64String($ba, 0, $want) -ne [System.Convert]::ToBase64String($bb, 0, $want)) { return $false }
            $left -= $want
        }
        return $true
    } finally { $fa.Dispose(); $fb.Dispose() }
}
try {
    foreach ($e in $entries) {
        if (-not (Test-SameRange $tmp $e.Offset $e.File $e.SrcOffset $e.Size)) {
            throw "Verification failed for $($e.Name); nothing was installed."
        }
    }
} catch {
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    throw
}

Move-Item -LiteralPath $tmp -Destination $target -Force
Set-Content -LiteralPath $marker -Value 'Test archive created by tools/archive/New-TestArchive.ps1. Remove with -Remove.'
Write-Host ("Wrote {0} ({1:N0} bytes) with {2} entries:" -f $target, $total, $entries.Count)
foreach ($e in $entries) { Write-Host ("  #{0:X8}  {1,-42} {2,12:N0} bytes, copied from {3}" -f $e.Hash, $e.Name, $e.Size, (Split-Path $e.File -Leaf)) }
