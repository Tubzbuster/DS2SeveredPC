<#
.SYNOPSIS
    Copies a fixed set of sample files out of the PC game, the Xbox 360 game
    and the extracted Severed DLC, for building the 360 -> PC converter.

.DESCRIPTION
    The same files are exported from both platforms (PC DS2DAT*.DAT and 360
    bigfile*.viv archives) so they can be compared side by side, plus key
    Severed files. Results go to out\PC, out\360 and out\Severed next to this
    script, with index.csv listing what was found, and out\samples.zip
    containing everything.

    Archive entries are located by name hash (sdbm of the lowercase path with
    backslashes, e.g. "ch01_hos\ch01_hos.toc").

    These are EA's files: share the zip privately and remove the link
    afterwards.

.PARAMETER PcDir
    PC install folder (contains DS2DAT0.DAT).

.PARAMETER X360Dir
    Folder with the extracted Xbox 360 discs (searched for *.viv).

.PARAMETER SeveredDir
    Folder with the extracted Severed DLC (contains weller1.lvl, either
    directly or one folder down).
#>
[CmdletBinding()]
param(
    [string]$PcDir,
    [string]$X360Dir,
    [string]$SeveredDir,
    [string]$OutDir
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# Files wanted from both platforms' archives, by path.
$names = @(
    'ch01_hos\ch01_hos.toc', 'ch01_hos\ch01_hos_global.toc', 'ch01_hos\ch01_hos.str',
    'ch01_hos\ch01_hos_global.str', 'ch01_hos\ch01_hos_streamsets.str',
    'ch09_mng\ch09_mng.toc', 'ch09_mng\ch09_mng_global.toc', 'ch09_mng\ch09_mng.str',
    'ch09_mng\ch09_mng_global.str', 'ch09_mng\ch09_mng_streamsets.str',
    'frontend\frontend.toc', 'frontend\frontend_global.toc', 'frontend\frontend.str',
    'frontend\frontend_global.str',
    'global_assets\global_assets.toc', 'global_assets\global_assets_global.toc',
    'global_assets\global_assets_global.str'
)
# Files wanted by hash only (name not known yet): level streams, audio, text.
$hashes = @(
    '4564F3D7', '020C6F8C', '08AAE462',             # level streams
    '923A6A91', '9900005D', 'FA7816F1', 'A0AB92F3', # audio (.snu)
    'E4529CFE', '78E854C7', 'B5B3941D', '9B597F7F'  # chapter list, version, scripts
)
# Files wanted from the extracted Severed DLC, by path inside the package.
$severedFiles = @(
    'weller1.dlm', 'weller1.key', 'weller1.lds', 'weller1.lvl', 'weller1.pid',
    'global_assets_global.add', 'pdlc1_ch01_mng.add',
    'global_assets\global_assets_global.str',
    'pdlc1_ch01_mng\pdlc1_ch01_mng.toc', 'pdlc1_ch01_mng\pdlc1_ch01_mng_global.toc',
    'pdlc1_ch01_mng\pdlc1_ch01_mng.str', 'pdlc1_ch01_mng\pdlc1_ch01_mng_global.str',
    'pdlc1_ch01_mng\pdlc1_ch01_mng\dlc_support\level_select.str',
    'audiostreams\pdlc1_se_02_15b.exa.snu', 'audiostreams\mx_pdlc1_igc_02_02.exa.snu',
    'movies\en\pdlc1_vt_02_01.vp6'
)

function Get-NameHash([string]$name) {
    $h = [uint64]0
    foreach ($c in [System.Text.Encoding]::ASCII.GetBytes($name.ToLowerInvariant())) {
        $h = ($h * 65599 + $c) % 4294967296
    }
    return ('{0:X8}' -f $h)
}

function Read-Exact($fs, [int64]$offset, [int]$count) {
    $buf = New-Object byte[] $count
    $fs.Position = $offset
    $read = 0
    while ($read -lt $count) {
        $n = $fs.Read($buf, $read, $count - $read)
        if ($n -le 0) { throw "Unexpected end of file at 0x$('{0:X}' -f $offset)" }
        $read += $n
    }
    return , $buf
}

function U32BE([byte[]]$b, [int]$o) {
    return ([uint32]$b[$o] -shl 24) -bor ([uint32]$b[$o + 1] -shl 16) -bor ([uint32]$b[$o + 2] -shl 8) -bor [uint32]$b[$o + 3]
}

# Returns hash -> @{Archive; Offset; Size} for the first archive holding each hash.
function Read-Directories([System.IO.FileInfo[]]$archives) {
    $map = @{}
    foreach ($a in $archives) {
        $fs = [System.IO.File]::Open($a.FullName, 'Open', 'Read', 'ReadWrite')
        try {
            $h = Read-Exact $fs 0 16
            if ([System.Text.Encoding]::ASCII.GetString($h, 0, 4) -ne 'BIGH') { Write-Warning "$($a.Name) is not a BIGH archive"; continue }
            $count = [int](U32BE $h 8)
            $dir = Read-Exact $fs 16 ($count * 12)
            for ($i = 0; $i -lt $count; $i++) {
                $key = '{0:X8}' -f (U32BE $dir ($i * 12 + 8))
                if (-not $map.ContainsKey($key)) {
                    $map[$key] = @{ Archive = $a.FullName; Offset = [int64](U32BE $dir ($i * 12)); Size = [int64](U32BE $dir ($i * 12 + 4)) }
                }
            }
        } finally { $fs.Dispose() }
    }
    return $map
}

function Copy-Range([string]$src, [int64]$offset, [int64]$size, [string]$dest) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    $in = [System.IO.File]::Open($src, 'Open', 'Read', 'ReadWrite')
    $out = [System.IO.File]::Create($dest)
    try {
        $in.Position = $offset
        $buf = New-Object byte[] 1048576
        $left = $size
        while ($left -gt 0) {
            $n = $in.Read($buf, 0, [int][Math]::Min($buf.Length, $left))
            if ($n -le 0) { throw 'short read' }
            $out.Write($buf, 0, $n)
            $left -= $n
        }
    } finally { $out.Dispose(); $in.Dispose() }
}

if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot 'out' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$index = New-Object System.Collections.Generic.List[object]

function Export-FromArchives([string]$platform, [System.IO.FileInfo[]]$archives) {
    if (-not $archives -or $archives.Count -eq 0) { Write-Warning "No archives found for $platform"; return }
    Write-Host "Reading $($archives.Count) $platform archive director(ies)..."
    $map = Read-Directories $archives
    $wanted = New-Object System.Collections.Generic.List[object]
    foreach ($n in $names) { $wanted.Add(@{ Name = $n; Hash = (Get-NameHash $n) }) }
    foreach ($h in $hashes) { $wanted.Add(@{ Name = "#$h.bin"; Hash = $h }) }
    foreach ($w in $wanted) {
        $e = $map[$w.Hash]
        if (-not $e) {
            $index.Add([pscustomobject]@{ Platform = $platform; Name = $w.Name; Hash = $w.Hash; Source = '(not found)'; Size = 0; SHA256 = '' })
            continue
        }
        $dest = Join-Path (Join-Path $OutDir $platform) $w.Name
        Write-Host ("  {0,-45} {1,12:N0} bytes from {2}" -f $w.Name, $e.Size, (Split-Path $e.Archive -Leaf))
        Copy-Range $e.Archive $e.Offset $e.Size $dest
        $index.Add([pscustomobject]@{ Platform = $platform; Name = $w.Name; Hash = $w.Hash; Source = (Split-Path $e.Archive -Leaf); Size = $e.Size; SHA256 = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash })
    }
}

if ($PcDir) {
    Export-FromArchives 'PC' @(Get-ChildItem -LiteralPath $PcDir -Filter 'DS2DAT*.DAT' -File | Sort-Object Name)
}
if ($X360Dir) {
    Export-FromArchives '360' @(Get-ChildItem -LiteralPath $X360Dir -Filter '*.viv' -File -Recurse | Sort-Object FullName)
}
if ($SeveredDir) {
    $root = $SeveredDir
    if (-not (Test-Path -LiteralPath (Join-Path $root 'weller1.lvl'))) {
        $sub = Get-ChildItem -LiteralPath $root -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'weller1.lvl') } | Select-Object -First 1
        if ($sub) { $root = $sub.FullName } else { Write-Warning "weller1.lvl not found in $SeveredDir or one folder below it" }
    }
    Write-Host "Copying Severed files from $root"
    foreach ($rel in $severedFiles) {
        $src = Join-Path $root $rel
        if (-not (Test-Path -LiteralPath $src)) {
            $index.Add([pscustomobject]@{ Platform = 'Severed'; Name = $rel; Hash = (Get-NameHash $rel); Source = '(not found)'; Size = 0; SHA256 = '' })
            continue
        }
        $dest = Join-Path (Join-Path $OutDir 'Severed') $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dest -Force
        $len = (Get-Item -LiteralPath $dest).Length
        Write-Host ("  {0,-45} {1,12:N0} bytes" -f $rel, $len)
        $index.Add([pscustomobject]@{ Platform = 'Severed'; Name = $rel; Hash = (Get-NameHash $rel); Source = 'extracted'; Size = $len; SHA256 = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash })
    }
}

$index | Export-Csv -LiteralPath (Join-Path $OutDir 'index.csv') -NoTypeInformation -Encoding UTF8
$zip = Join-Path $OutDir 'samples.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
$items = @(Get-ChildItem -LiteralPath $OutDir | Where-Object { $_.Name -ne 'samples.zip' } | ForEach-Object { $_.FullName })
if ($items.Count -gt 0) { Compress-Archive -Path $items -DestinationPath $zip }
$missing = @($index | Where-Object { $_.Source -eq '(not found)' }).Count
Write-Host ''
Write-Host "Done. $($index.Count - $missing) files exported, $missing not found (see index.csv)."
Write-Host "Zip: $zip"
