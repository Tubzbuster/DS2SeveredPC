<#
.SYNOPSIS
    Copies selected assets (raw, as stored) out of the PC and Xbox 360
    archives, so PC and 360 versions of the same assets can be compared to
    build the converter.

.DESCRIPTION
    wanted.txt (next to this script) lists what to export, one rule per line:

        Material                 every asset of that type
        Mesh<TAB>some_mesh_name  one asset, by type and name

    For every level stream (.str) inside DS2DAT*.DAT (PC) and bigfile*.viv
    (360), each asset matching a rule is copied once: its header chunk and
    data chunks, exactly as stored. The results are themselves stream files:

        out\pc_assets.str     PC versions
        out\x360_assets.str   Xbox 360 versions
        out\assets_export.zip both, zipped

    These contain EA's data: share them privately.

.PARAMETER GameDir
    PC Dead Space 2 folder (with DS2DAT0.DAT).

.PARAMETER X360Dir
    Folder with the extracted Xbox 360 discs (searched for *.viv).
#>
[CmdletBinding()]
param(
    [string]$GameDir,
    [string]$X360Dir,
    [string]$ListFile,
    [string]$OutDir
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Write-Host 'Export-AssetPairs version 1'

if (-not $ListFile) { $ListFile = Join-Path $PSScriptRoot 'wanted.txt' }
if (-not (Test-Path -LiteralPath $ListFile)) {
    throw "The export list was not found at $ListFile. Keep wanted.txt in the same folder as this script (it is in the repo's tools\export folder), or give its path with -ListFile."
}
if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot 'out' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$allOfType = New-Object 'System.Collections.Generic.HashSet[string]'
$named = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($line in [System.IO.File]::ReadAllLines($ListFile)) {
    $l = $line.Trim()
    if ($l -eq '' -or $l.StartsWith('#')) { continue }
    $parts = $l -split "`t", 2
    if ($parts.Count -eq 1) { [void]$allOfType.Add($parts[0]) }
    else { [void]$named.Add($parts[0] + "`t" + $parts[1].ToLowerInvariant()) }
}
Write-Host ("Rules: {0} whole types, {1} named assets" -f $allOfType.Count, $named.Count)

function U32([byte[]]$b, [int]$o, [bool]$be) {
    if ($be) { return ([uint32]$b[$o] -shl 24) -bor ([uint32]$b[$o + 1] -shl 16) -bor ([uint32]$b[$o + 2] -shl 8) -bor [uint32]$b[$o + 3] }
    return [System.BitConverter]::ToUInt32($b, $o)
}
function Tag([byte[]]$b, [int]$o, [bool]$be) {
    $s = [System.Text.Encoding]::ASCII.GetString($b, $o, 4)
    if ($be) { return $s }
    $c = $s.ToCharArray(); [array]::Reverse($c); return -join $c
}
function CStrEnd([byte[]]$b, [int]$o, [int]$end) {
    while ($o -lt $end -and $b[$o] -ne 0) { $o++ }
    return $o
}

# Copies the wanted assets of one stream file $d to $out; returns bytes written.
function Export-Stream([byte[]]$d, $out, $seen) {
    $be = [System.Text.Encoding]::ASCII.GetString($d, 0, 4) -eq 'ols3'
    $latin = [System.Text.Encoding]::GetEncoding(28591)
    $o = 12
    $copying = $false
    $written = 0
    while ($o + 12 -le $d.Length) {
        $size = [int64](U32 $d ($o + 4) $be)
        if ($size -lt 8 -or $o + $size -gt $d.Length) { break }
        $isShoc = (Tag $d $o $be) -eq 'SHOC'
        if ($isShoc -and (Tag $d ($o + 8) $be) -eq 'SHDR' -and $size -ge 44) {
            $end = [int]($o + $size)
            $n1 = CStrEnd $d ($o + 44) $end
            $name = $latin.GetString($d, $o + 44, $n1 - $o - 44)
            $n2 = CStrEnd $d ($n1 + 1) $end
            $n3 = CStrEnd $d ($n2 + 1) $end
            $type = $latin.GetString($d, $n2 + 1, $n3 - $n2 - 1)
            $copying = $false
            if ($allOfType.Contains($type) -or $named.Contains($type + "`t" + $name.ToLowerInvariant())) {
                $key = '{0}|{1}|{2:X8}{3:X8}{4:X8}{5:X8}{6:X8}' -f $type, $name.ToLowerInvariant(), (U32 $d ($o + 20) $be), (U32 $d ($o + 24) $be), (U32 $d ($o + 28) $be), (U32 $d ($o + 32) $be), (U32 $d ($o + 36) $be)
                if ($seen.Add($key)) { $copying = $true }
            }
        }
        if ($copying -and $isShoc) { $out.Write($d, $o, [int]$size); $written += $size }
        $o += [int]$size
    }
    return $written
}

function Export-Platform([string]$label, [System.IO.FileInfo[]]$archives, [string]$magic, [string]$outFile) {
    if (-not $archives -or $archives.Count -eq 0) { Write-Warning "No archives found for $label"; return $null }
    $out = [System.IO.File]::Create($outFile)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    $headerWritten = $false
    $total = [int64]0
    try {
        foreach ($a in $archives) {
            $fs = [System.IO.File]::Open($a.FullName, 'Open', 'Read', 'ReadWrite')
            try {
                $h = New-Object byte[] 16
                [void]$fs.Read($h, 0, 16)
                if ([System.Text.Encoding]::ASCII.GetString($h, 0, 4) -ne 'BIGH') { continue }
                $count = [int](U32 $h 8 $true)
                $dir = New-Object byte[] ($count * 12)
                $fs.Position = 16
                $got = 0; while ($got -lt $dir.Length) { $got += $fs.Read($dir, $got, $dir.Length - $got) }
                Write-Host ("{0} {1}: {2} entries" -f $label, $a.Name, $count)
                $m = New-Object byte[] 12
                for ($i = 0; $i -lt $count; $i++) {
                    $off = [int64](U32 $dir ($i * 12) $true)
                    $len = [int](U32 $dir ($i * 12 + 4) $true)
                    if ($len -lt 12) { continue }
                    $fs.Position = $off
                    [void]$fs.Read($m, 0, 12)
                    if ([System.Text.Encoding]::ASCII.GetString($m, 0, 4) -ne $magic) { continue }
                    if (($i % 20) -eq 0) { Write-Progress -Activity "Exporting from $($a.Name)" -Status "$i / $count" -PercentComplete ([int](100 * $i / $count)) }
                    if (-not $headerWritten) { $out.Write($m, 0, 12); $headerWritten = $true }
                    $d = New-Object byte[] $len
                    $fs.Position = $off
                    $got = 0; while ($got -lt $len) { $r = $fs.Read($d, $got, $len - $got); if ($r -le 0) { break }; $got += $r }
                    $total += Export-Stream $d $out $seen
                }
                Write-Progress -Activity "Exporting from $($a.Name)" -Completed
            } finally { $fs.Dispose() }
        }
    } finally { $out.Dispose() }
    Write-Host ("{0}: {1} assets, {2:N1} MB -> {3}" -f $label, $seen.Count, ($total / 1MB), $outFile)
    return $outFile
}

$files = New-Object System.Collections.Generic.List[string]
if ($GameDir) {
    $f = Export-Platform 'PC' @(Get-ChildItem -LiteralPath $GameDir -Filter 'DS2DAT*.DAT' -File | Sort-Object Name) '3slo' (Join-Path $OutDir 'pc_assets.str')
    if ($f) { $files.Add($f) }
}
if ($X360Dir) {
    $f = Export-Platform '360' @(Get-ChildItem -LiteralPath $X360Dir -Filter '*.viv' -File -Recurse | Sort-Object FullName) 'ols3' (Join-Path $OutDir 'x360_assets.str')
    if ($f) { $files.Add($f) }
}
if ($files.Count -eq 0) { Write-Warning 'Nothing exported: give -GameDir and/or -X360Dir.'; return }
$zip = Join-Path $OutDir 'assets_export.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path $files.ToArray() -DestinationPath $zip
Write-Host "Zip: $zip"
