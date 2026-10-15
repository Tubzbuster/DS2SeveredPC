<#
.SYNOPSIS
    Lists every asset header inside the game's level streams (.str), for
    the PC archives and/or an extracted Severed folder.

.DESCRIPTION
    Stream files hold assets (textures, meshes, scripts, ...), each with a
    header giving its type, name and content IDs. Severed assets whose
    (type, name, IDs) match a PC asset can be taken from the PC game instead
    of converted. This writes those headers, no asset data, to:

        out\assets_pc.csv       one row per asset in DS2DAT*.DAT streams
        out\assets_severed.csv  one row per asset in the Severed .str files
        out\assets.zip          both, zipped

    Columns: Source (archive or relative path), Entry (archive entry hash),
    Platform, Type, Name, TypeHash, Flags, Id0..Id4, Size (uncompressed),
    Chunks (data chunk kinds).

.PARAMETER GameDir
    PC Dead Space 2 folder (with DS2DAT0.DAT).

.PARAMETER SeveredDir
    Extracted Severed folder (searched for *.str).
#>
[CmdletBinding()]
param(
    [string]$GameDir,
    [string]$SeveredDir,
    [string]$OutDir
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Write-Host 'Index-Assets version 1'

if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot 'out' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function U32([byte[]]$b, [int]$o, [bool]$be) {
    if ($be) { return ([uint32]$b[$o] -shl 24) -bor ([uint32]$b[$o + 1] -shl 16) -bor ([uint32]$b[$o + 2] -shl 8) -bor [uint32]$b[$o + 3] }
    return [System.BitConverter]::ToUInt32($b, $o)
}
function U16([byte[]]$b, [int]$o, [bool]$be) {
    if ($be) { return ([int]$b[$o] -shl 8) -bor [int]$b[$o + 1] }
    return [int][System.BitConverter]::ToUInt16($b, $o)
}
function Tag([byte[]]$b, [int]$o, [bool]$be) {
    $s = [System.Text.Encoding]::ASCII.GetString($b, $o, 4)
    if ($be) { return $s }
    $c = $s.ToCharArray(); [array]::Reverse($c); return -join $c
}
function CStr([byte[]]$b, [int]$o, [int]$end) {
    $i = $o
    while ($i -lt $end -and $b[$i] -ne 0) { $i++ }
    return @([System.Text.Encoding]::GetEncoding(28591).GetString($b, $o, $i - $o), ($i + 1))
}

# Walks one stream file held in $d and writes a CSV line per asset.
function Write-Assets([byte[]]$d, [string]$source, [string]$entry, $writer) {
    if ($d.Length -lt 12) { return 0 }
    $magic = [System.Text.Encoding]::ASCII.GetString($d, 0, 4)
    if ($magic -eq 'ols3') { $be = $true; $plat = '360' } elseif ($magic -eq '3slo') { $be = $false; $plat = 'PC' } else { return 0 }
    $o = 12
    $n = 0
    $cur = $null
    $chunks = New-Object System.Collections.Generic.List[string]
    while ($o + 12 -le $d.Length) {
        $size = [int64](U32 $d ($o + 4) $be)
        if ($size -lt 8 -or $o + $size -gt $d.Length) { break }
        if ((Tag $d $o $be) -eq 'SHOC') {
            $sub = Tag $d ($o + 8) $be
            if ($sub -eq 'SHDR' -and $size -ge 44) {
                if ($null -ne $cur) { $writer.WriteLine($cur + ',' + ($chunks -join '+')); $n++ }
                $chunks.Clear()
                $end = [int]($o + $size)
                $r = CStr $d ($o + 44) $end; $name = $r[0]
                $r2 = CStr $d $r[1] $end
                $r3 = CStr $d $r2[1] $end; $type = $r3[0]
                $f = '{0},{1},{2},"{3}","{4}",{5:X8},{6}.{7},{8:X8},{9:X8},{10:X8},{11:X8},{12:X8},{13}' -f `
                    $source, $entry, $plat, $type, $name.Replace('"', '""'), (U32 $d ($o + 12) $be), (U16 $d ($o + 16) $be), (U16 $d ($o + 18) $be),
                    (U32 $d ($o + 20) $be), (U32 $d ($o + 24) $be), (U32 $d ($o + 28) $be), (U32 $d ($o + 32) $be), (U32 $d ($o + 36) $be), (U32 $d ($o + 40) $be)
                $cur = $f
            } elseif ($null -ne $cur) {
                $chunks.Add($sub)
            }
        }
        $o += [int]$size
    }
    if ($null -ne $cur) { $writer.WriteLine($cur + ',' + ($chunks -join '+')); $n++ }
    return $n
}

$header = 'Source,Entry,Platform,Type,Name,TypeHash,Flags,Id0,Id1,Id2,Id3,Id4,Size,Chunks'
$files = New-Object System.Collections.Generic.List[string]

if ($GameDir) {
    $csv = Join-Path $OutDir 'assets_pc.csv'
    $w = New-Object System.IO.StreamWriter($csv, $false, (New-Object System.Text.UTF8Encoding($false)))
    $w.WriteLine($header)
    $total = 0
    try {
        foreach ($a in (Get-ChildItem -LiteralPath $GameDir -Filter 'DS2DAT*.DAT' -File | Sort-Object Name)) {
            $fs = [System.IO.File]::Open($a.FullName, 'Open', 'Read', 'ReadWrite')
            try {
                $h = New-Object byte[] 16
                [void]$fs.Read($h, 0, 16)
                if ([System.Text.Encoding]::ASCII.GetString($h, 0, 4) -ne 'BIGH') { continue }
                $count = [int](U32 $h 8 $true)
                $dir = New-Object byte[] ($count * 12)
                $fs.Position = 16
                $got = 0; while ($got -lt $dir.Length) { $got += $fs.Read($dir, $got, $dir.Length - $got) }
                Write-Host ("{0}: {1} entries" -f $a.Name, $count)
                for ($i = 0; $i -lt $count; $i++) {
                    $off = [int64](U32 $dir ($i * 12) $true)
                    $len = [int](U32 $dir ($i * 12 + 4) $true)
                    $hash = '{0:X8}' -f (U32 $dir ($i * 12 + 8) $true)
                    if ($len -lt 12) { continue }
                    $fs.Position = $off
                    $m = New-Object byte[] 4
                    [void]$fs.Read($m, 0, 4)
                    if ([System.Text.Encoding]::ASCII.GetString($m, 0, 4) -ne '3slo') { continue }
                    if (($i % 20) -eq 0) { Write-Progress -Activity "Indexing $($a.Name)" -Status "$i / $count" -PercentComplete ([int](100 * $i / $count)) }
                    $d = New-Object byte[] $len
                    $fs.Position = $off
                    $got = 0; while ($got -lt $len) { $r = $fs.Read($d, $got, $len - $got); if ($r -le 0) { break }; $got += $r }
                    $total += Write-Assets $d $a.Name $hash $w
                }
                Write-Progress -Activity "Indexing $($a.Name)" -Completed
            } finally { $fs.Dispose() }
        }
    } finally { $w.Dispose() }
    Write-Host "PC: $total assets -> $csv"
    $files.Add($csv)
}

if ($SeveredDir) {
    $csv = Join-Path $OutDir 'assets_severed.csv'
    $w = New-Object System.IO.StreamWriter($csv, $false, (New-Object System.Text.UTF8Encoding($false)))
    $w.WriteLine($header)
    $total = 0
    try {
        $root = (Resolve-Path -LiteralPath $SeveredDir).ProviderPath.TrimEnd('\', '/')
        foreach ($f in (Get-ChildItem -LiteralPath $root -Filter '*.str' -File -Recurse | Sort-Object FullName)) {
            $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/')
            $total += Write-Assets ([System.IO.File]::ReadAllBytes($f.FullName)) $rel '' $w
        }
    } finally { $w.Dispose() }
    Write-Host "Severed: $total assets -> $csv"
    $files.Add($csv)
}

if ($files.Count -eq 0) { Write-Warning 'Nothing to do: give -GameDir and/or -SeveredDir.'; return }
$zip = Join-Path $OutDir 'assets.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path $files.ToArray() -DestinationPath $zip
Write-Host "Zip: $zip"
