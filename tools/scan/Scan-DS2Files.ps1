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
      packages.txt     decoded header and full file listing of any Xbox 360
                       STFS package (CON/LIVE/PIRS), e.g. the Severed DLC file
      archives.txt     directory summary of EA BIGH archives (PC DS2DAT*.DAT,
                       Xbox 360 bigfile*.viv); their entries are in the manifest
                       as "<archive>::#<name hash>"
      smallfiles.txt   full contents of small descriptor/config files
                       (.toc .add .dlm .key .lds .lvl .pid .txt .xml ...)
      executables.txt  PE (.exe/.dll) and XEX details, plus content/DLC-related
                       strings found inside them

    Files inside Xbox 360 packages are read in place and appear in the
    manifest as "<package>::<path inside package>", so the Severed DLC file
    does not need extracting first.

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
    Where the scan folder is created. Defaults to a scans\ folder next to
    this script.

.PARAMETER ExtractTo
    Optional. Also extract the contents of any Xbox 360 package into this
    folder (one subfolder per package). Keep it outside the git repo.

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
    [string]$ExtractTo,
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
        'ols3' { return 'Visceral stream (ols3)' }
        '3slo' { return 'Visceral stream (3slo, byte-swapped)' }
        'XDBF' { return 'X360 XDBF (achievements/SPA)' }
        'MVhd' { return 'EA VP6 video (MVhd)' }
        'MSCF' { return 'Microsoft CAB' }
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

# --------------------------------------------------------------------------
# Xbox 360 STFS package reader (CON/LIVE/PIRS)
# Layout and block maths follow the Free60 STFS documentation and Velocity.
# --------------------------------------------------------------------------

function Read-At($fs, [int64]$offset, [int]$count) {
    $buf = New-Object byte[] $count
    $fs.Position = $offset
    $read = 0
    while ($read -lt $count) {
        $n = $fs.Read($buf, $read, $count - $read)
        if ($n -le 0) { break }
        $read += $n
    }
    if ($read -lt $count) { throw ('Unexpected end of package reading 0x{0:X} bytes at 0x{1:X}' -f $count, $offset) }
    return , $buf
}

function IDiv([int64]$a, [int64]$b) { return [int64][Math]::Floor($a / $b) }
function Int24LE([byte[]]$b, [int]$o) { return [int64]$b[$o] -bor ([int64]$b[$o + 1] -shl 8) -bor ([int64]$b[$o + 2] -shl 16) }
function Int24BE([byte[]]$b, [int]$o) { return ([int64]$b[$o] -shl 16) -bor ([int64]$b[$o + 1] -shl 8) -bor [int64]$b[$o + 2] }

function Open-Stfs([string]$file) {
    $fs = [System.IO.File]::Open($file, 'Open', 'Read', 'ReadWrite')
    $h = Read-At $fs 0 0x3B0
    $headerSize = [int64](U32BE $h 0x340)
    $vd = 0x379
    $sep = [int]$h[$vd + 2]
    $sex = (-bnot $sep) -band 1          # 0 = "female" (1 table per level), 1 = "male" (2 tables)
    $alloc = [int64](U32BE $h ($vd + 0x1C))
    $p = [pscustomobject]@{
        Fs           = $fs
        DescType     = [int64](U32BE $h 0x3A9)
        HeaderSize   = $headerSize
        First        = [int64](IDiv ($headerSize + 0xFFF) 0x1000) * 0x1000
        Sep          = $sep
        Sex          = $sex
        Step0        = $(if ($sex -eq 0) { 0xAB } else { 0xAC })
        Step1        = $(if ($sex -eq 0) { 0x718F } else { 0x723A })
        FtBlockCount = [int64]$h[$vd + 3] -bor ([int64]$h[$vd + 4] -shl 8)
        FtBlock      = Int24LE $h ($vd + 5)
        Alloc        = $alloc
        Unalloc      = [int64](U32BE $h ($vd + 0x20))
        TopLevel     = $(if ($alloc -le 0xAA) { 0 } elseif ($alloc -le 0x70E4) { 1 } else { 2 })
        TopAddr      = [int64]0
        Entries      = $null
    }
    $topBacking = switch ($p.TopLevel) { 0 { 0 } 1 { $p.Step0 } 2 { $p.Step1 } }
    $p.TopAddr = ([int64]$topBacking -shl 12) + $p.First + (([int64]($sep -band 2)) -shl 11)
    return $p
}

function Stfs-DataBlock($p, [int64]$n) {
    $s = $p.Sex
    $r = ((IDiv ($n + 0xAA) 0xAA) -shl $s) + $n
    if ($n -lt 0xAA) { return $r }
    if ($n -lt 0x70E4) { return $r + ((IDiv ($n + 0x70E4) 0x70E4) -shl $s) }
    return (1 -shl $s) + $r + ((IDiv ($n + 0x70E4) 0x70E4) -shl $s)
}

function Stfs-BlockAddr($p, [int64]$n) { return ((Stfs-DataBlock $p $n) -shl 12) + $p.First }

function Stfs-L0Backing($p, [int64]$n) {
    if ($n -lt 0xAA) { return [int64]0 }
    $num = (IDiv $n 0xAA) * $p.Step0 + (((IDiv $n 0x70E4) + 1) -shl $p.Sex)
    if ((IDiv $n 0x70E4) -eq 0) { return $num }
    return $num + (1 -shl $p.Sex)
}

function Stfs-L1Backing($p, [int64]$n) {
    if ($n -lt 0x70E4) { return [int64]$p.Step0 }
    return (1 -shl $p.Sex) + (IDiv $n 0x70E4) * $p.Step1
}

function Stfs-NextBlock($p, [int64]$n) {
    $addr = ((Stfs-L0Backing $p $n) -shl 12) + $p.First + ($n % 0xAA) * 0x18
    switch ($p.TopLevel) {
        0 { $addr += ([int64]($p.Sep -band 2)) -shl 11 }
        1 {
            $st = (Read-At $p.Fs ($p.TopAddr + (IDiv $n 0xAA) * 0x18 + 0x14) 1)[0]
            $addr += ([int64]($st -band 0x40)) -shl 6
        }
        2 {
            $st2 = (Read-At $p.Fs ($p.TopAddr + (IDiv $n 0x70E4) * 0x18 + 0x14) 1)[0]
            $l1 = ((Stfs-L1Backing $p $n) -shl 12) + $p.First + (([int64]($st2 -band 0x40)) -shl 6)
            $st1 = (Read-At $p.Fs ($l1 + ((IDiv $n 0xAA) % 0xAA) * 0x18 + 0x14) 1)[0]
            $addr += ([int64]($st1 -band 0x40)) -shl 6
        }
    }
    $e = Read-At $p.Fs $addr 0x18
    return Int24BE $e 0x15
}

function FatTime([int64]$v) {
    $d = ($v -shr 16) -band 0xFFFF; $t = $v -band 0xFFFF
    try { return (Get-Date -Year ((($d -shr 9) -band 0x7F) + 1980) -Month (($d -shr 5) -band 0xF) -Day ($d -band 0x1F) `
                         -Hour (($t -shr 11) -band 0x1F) -Minute (($t -shr 5) -band 0x3F) -Second (($t -band 0x1F) * 2)).ToString('yyyy-MM-dd HH:mm:ss') }
    catch { return ('0x{0:X8}' -f $v) }
}

function Get-StfsEntries($p) {
    $entries = New-Object System.Collections.Generic.List[object]
    $block = $p.FtBlock
    for ($i = 0; $i -lt $p.FtBlockCount; $i++) {
        $b = Read-At $p.Fs (Stfs-BlockAddr $p $block) 0x1000
        for ($e = 0; $e -lt 0x40; $e++) {
            $o = $e * 0x40
            $flags = $b[$o + 0x28]
            $nameLen = $flags -band 0x3F
            if ($nameLen -eq 0) { continue }
            $entries.Add([pscustomobject]@{
                Index      = $entries.Count
                Name       = [System.Text.Encoding]::ASCII.GetString($b, $o, [Math]::Min($nameLen, 0x28))
                IsDir      = [bool]($flags -band 0x80)
                Consecutive = [bool]($flags -band 0x40)
                Blocks     = Int24LE $b ($o + 0x29)
                StartBlock = Int24LE $b ($o + 0x2F)
                Parent     = [int](([int]$b[$o + 0x32] -shl 8) -bor $b[$o + 0x33])
                Size       = [int64](U32BE $b ($o + 0x34))
                Created    = FatTime (U32BE $b ($o + 0x38))
                Path       = ''
            })
        }
        if ($i -lt $p.FtBlockCount - 1) {
            $next = Stfs-NextBlock $p $block
            if ($next -ge $p.Alloc -or $next -eq 0xFFFFFF) { $next = $block + 1 }
            $block = $next
        }
    }
    foreach ($en in $entries) {
        $parts = New-Object System.Collections.Generic.List[string]
        $parts.Add($en.Name)
        $cur = $en.Parent
        $guard = 0
        while ($cur -ne 0xFFFF -and $cur -ge 0 -and $cur -lt $entries.Count -and $guard -lt 64) {
            $parts.Insert(0, $entries[$cur].Name); $cur = $entries[$cur].Parent; $guard++
        }
        $en.Path = $parts -join '/'
    }
    $p.Entries = $entries
    return , $entries
}

# Streams a file out of the package, calling $sink with (buffer, count) for each block.
function Read-StfsFile($p, $entry, [int64]$maxBytes, [scriptblock]$sink) {
    $remaining = [Math]::Min($entry.Size, $maxBytes)
    $block = $entry.StartBlock
    $i = 0
    while ($remaining -gt 0) {
        $n = [int][Math]::Min(0x1000, $remaining)
        $buf = Read-At $p.Fs (Stfs-BlockAddr $p $block) $n
        & $sink $buf $n
        $remaining -= $n
        $i++
        if ($remaining -gt 0) {
            if ($entry.Consecutive) { $block = $entry.StartBlock + $i }
            else {
                $block = Stfs-NextBlock $p $block
                if ($block -ge $p.Alloc) { throw ('Broken block chain in {0} (next block 0x{1:X})' -f $entry.Path, $block) }
            }
        }
    }
}

function Read-StfsHead($p, $entry, [int]$count) {
    $ms = New-Object System.IO.MemoryStream
    Read-StfsFile $p $entry $count { param($buf, $n) $ms.Write($buf, 0, $n) }
    return , $ms.ToArray()
}

$keywordPattern = 'dlc|pdlc|sever|weller|lexine|titan|download|marketplace|entitle|content|package|mount|chapter|bundle|level_select|xcontent|\.lvl\b|\.lds\b|\.pid\b|\.dlm\b|\.key\b|\.add\b|\.snu\b|\.vp6\b|bigfile|ds2dat|\.str\b|\.viv\b|\.big\b|\.toc\b|\.sb\b|\.arc\b|\.ini\b|\.cfg\b'

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

if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot 'scans' }
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]', '_')
$dest = Join-Path $OutDir $safeLabel
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if ($ExtractTo) { New-Item -ItemType Directory -Force -Path $ExtractTo | Out-Null; $ExtractTo = (Resolve-Path -LiteralPath $ExtractTo).ProviderPath }

Write-Host "Scanning $root"
Write-Host "Writing to $dest"

$files = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue | Sort-Object FullName)
$total = $files.Count
Write-Host "$total files found"

$headLen = [Math]::Max([Math]::Max($HeaderBytes, $SampleBytes), 64)
$rows = New-Object System.Collections.Generic.List[object]
$heads = New-Object 'System.Collections.Generic.Dictionary[string,byte[]]'
$exes = New-Object System.Collections.Generic.List[object]
$pkgLines = New-Object System.Collections.Generic.List[string]
$errors = New-Object System.Collections.Generic.List[string]
$stfsCount = 0
$bigCount = 0
$bigLines = New-Object System.Collections.Generic.List[string]
$smallLines = New-Object System.Collections.Generic.List[string]
$sw = [System.Diagnostics.Stopwatch]::StartNew()

function Add-Row([string]$rel, [string]$ext, [int64]$size, [string]$hash, [byte[]]$head) {
    $fmt = Guess-Format $head
    $rows.Add([pscustomobject]@{
        RelativePath = $rel
        Extension    = $ext.ToLowerInvariant()
        Size         = $size
        SHA256       = $hash
        Magic        = (Magic-Text $head)
        Format       = $fmt
        HeaderHex    = (To-Hex $head $HeaderBytes)
    })
    $heads[$rel] = $head
    return $fmt
}


# EA BIGH archives (PC DS2DAT*.DAT and Xbox 360 bigfile*.viv).
# Layout seen in the scans: 'BIGH', u32 LE archive size, u32 BE entry count,
# u32 BE header size, then per entry u32 BE offset, u32 BE size, u32 BE name hash.
function Scan-Big([string]$full, [string]$rel) {
    $fs = [System.IO.File]::Open($full, 'Open', 'Read', 'ReadWrite')
    try {
        $h = Read-At $fs 0 16
        $count = [int64](U32BE $h 8)
        $hsz = [int64](U32BE $h 12)
        $bigLines.Add('')
        $bigLines.Add("== $rel")
        $bigLines.Add(('Archive size field : {0:N0} (file is {1:N0})' -f [System.BitConverter]::ToUInt32($h, 4), $fs.Length))
        $bigLines.Add(('Entries            : {0}' -f $count))
        $bigLines.Add(('Header size        : 0x{0:X}' -f $hsz))
        if ($count -le 0 -or 16 + $count * 12 -gt $hsz -or $hsz -gt $fs.Length) { $bigLines.Add('(directory does not match the expected layout; skipped)'); return }
        $dir = Read-At $fs 16 ([int]($count * 12))
        $extra = $hsz - 16 - $count * 12
        if ($extra -gt 0) {
            $t = Read-At $fs (16 + $count * 12) ([int][Math]::Min($extra, 64))
            $bigLines.Add(('Bytes after table  : {0}' -f (To-Hex $t 64)))
        }
        $magics = @{}
        for ($i = 0; $i -lt $count; $i++) {
            $off = [int64](U32BE $dir ($i * 12))
            $size = [int64](U32BE $dir ($i * 12 + 4))
            $nh = U32BE $dir ($i * 12 + 8)
            $innerRel = ('{0}::#{1:X8}' -f $rel, $nh)
            if (($i % 50) -eq 0) {
                Write-Progress -Id 1 -Activity "Reading archive $rel" -Status "$i / $count" -PercentComplete ([int](100 * $i / [Math]::Max(1, $count)))
            }
            try {
                if ($off + $size -gt $fs.Length) { throw ('entry runs past end of file (offset 0x{0:X}, size 0x{1:X})' -f $off, $size) }
                $head = Read-At $fs $off ([int][Math]::Min($size, $headLen))
                $hash = ''
                if (-not $SkipHash) {
                    $sha = [System.Security.Cryptography.SHA256]::Create()
                    $buf = New-Object byte[] 1048576
                    $fs.Position = $off
                    $left = $size
                    while ($left -gt 0) {
                        $n = $fs.Read($buf, 0, [int][Math]::Min($buf.Length, $left))
                        if ($n -le 0) { throw 'short read' }
                        [void]$sha.TransformBlock($buf, 0, $n, $null, 0)
                        $left -= $n
                    }
                    [void]$sha.TransformFinalBlock((New-Object byte[] 0), 0, 0)
                    $hash = ([System.BitConverter]::ToString($sha.Hash)).Replace('-', '')
                    $sha.Dispose()
                }
                $fmt = Add-Row $innerRel '(archive entry)' $size $hash $head
                $key = "'" + (Magic-Text $head) + "' " + $fmt
                if ($magics.ContainsKey($key)) { $magics[$key]++ } else { $magics[$key] = 1 }
            } catch {
                $errors.Add("$innerRel : $($_.Exception.Message)")
            }
        }
        Write-Progress -Id 1 -Activity "Reading archive $rel" -Completed
        $bigLines.Add('Entry types (by first 4 bytes):')
        foreach ($k in ($magics.GetEnumerator() | Sort-Object Value -Descending)) {
            $bigLines.Add(('  {0,6}  {1}' -f $k.Value, $k.Key))
        }
    } finally { $fs.Dispose() }
}

# Small descriptor/config files are dumped in full to smallfiles.txt.
$smallExts = @('.toc', '.add', '.dlm', '.key', '.lds', '.lvl', '.pid', '.txt', '.xml', '.ini', '.cfg', '.lng', '.manifest', '.vdf')
$smallMax = 65536
function Dump-Small([string]$rel, [byte[]]$data) {
    $smallLines.Add('')
    $smallLines.Add(('== {0}  ({1:N0} bytes)' -f $rel, $data.Length))
    if ((Guess-Format $data) -like 'text*' -or (Guess-Format $data) -eq 'XML') {
        $smallLines.Add([System.Text.Encoding]::GetEncoding(28591).GetString($data).TrimEnd())
    } else {
        foreach ($l in (Hex-Dump $data)) { $smallLines.Add($l) }
    }
}

function Scan-Package([string]$full, [string]$rel) {
    $pkgLines.Add('')
    foreach ($l in (Describe-Stfs $full $rel)) { $pkgLines.Add($l) }
    $p = Open-Stfs $full
    try {
        $pkgLines.Add(('Volume          : {0}, header size 0x{1:X}, first block at 0x{2:X}, block separation {3}, {4} hash levels' -f `
                       $(if ($p.DescType -eq 0) { 'STFS' } else { "type $($p.DescType) (not STFS)" }), $p.HeaderSize, $p.First, $p.Sep, ($p.TopLevel + 1)))
        $pkgLines.Add(('Blocks          : {0:N0} allocated, {1:N0} free; file table {2} block(s) from block {3}' -f $p.Alloc, $p.Unalloc, $p.FtBlockCount, $p.FtBlock))
        if ($p.DescType -ne 0) { $pkgLines.Add('(SVOD packages are not supported - extract this one with Velocity)'); return }
        $entries = @(Get-StfsEntries $p)
        $fileEntries = @($entries | Where-Object { -not $_.IsDir })
        $pkgLines.Add(('Contents        : {0} files, {1} folders' -f $fileEntries.Count, ($entries.Count - $fileEntries.Count)))
        $pkgLines.Add('')
        $pkgLines.Add(('  {0,-60} {1,15} {2,8} {3,-5} {4}' -f 'Path', 'Size', 'Blocks', 'Contig', 'Created'))
        foreach ($en in $entries) {
            $shown = if ($en.IsDir) { $en.Path + '/' } else { $en.Path }
            $pkgLines.Add(('  {0,-60} {1,15:N0} {2,8} {3,-5} {4}' -f $shown, $en.Size, $en.Blocks, $(if ($en.Consecutive) { 'yes' } else { 'no' }), $en.Created))
        }
        $k = 0
        foreach ($en in $fileEntries) {
            $k++
            $innerRel = "$rel::$($en.Path)"
            Write-Progress -Id 1 -Activity "Reading package $rel" -Status "$k / $($fileEntries.Count)  $($en.Path)" -PercentComplete ([int](100 * $k / [Math]::Max(1, $fileEntries.Count)))
            try {
                $script:pkgHead = New-Object System.IO.MemoryStream
                $sha = $null; $out = $null
                $outPath = $null
                if ($ExtractTo) {
                    $outPath = Join-Path (Join-Path $ExtractTo ([System.IO.Path]::GetFileName($rel))) ($en.Path -replace '/', [System.IO.Path]::DirectorySeparatorChar)
                    New-Item -ItemType Directory -Force -Path (Split-Path $outPath -Parent) | Out-Null
                    $out = [System.IO.File]::Create($outPath)
                }
                $limit = $en.Size
                if (-not $out -and $SkipHash) { $limit = $headLen }
                if (-not $SkipHash) { $sha = [System.Security.Cryptography.SHA256]::Create() }
                try {
                    Read-StfsFile $p $en $limit {
                        param($buf, $n)
                        if ($script:pkgHead.Length -lt $headLen) { $script:pkgHead.Write($buf, 0, [Math]::Min($n, $headLen - [int]$script:pkgHead.Length)) }
                        if ($sha) { [void]$sha.TransformBlock($buf, 0, $n, $null, 0) }
                        if ($out) { $out.Write($buf, 0, $n) }
                    }
                } finally { if ($out) { $out.Dispose() } }
                $hash = ''
                if ($sha) { [void]$sha.TransformFinalBlock((New-Object byte[] 0), 0, 0); $hash = ([System.BitConverter]::ToString($sha.Hash)).Replace('-', ''); $sha.Dispose() }
                $fmt = Add-Row $innerRel ([System.IO.Path]::GetExtension($en.Name)) $en.Size $hash $script:pkgHead.ToArray()
                if ($smallExts -contains [System.IO.Path]::GetExtension($en.Name).ToLowerInvariant() -and $en.Size -le $smallMax) {
                    $script:smallBuf = New-Object System.IO.MemoryStream
                    Read-StfsFile $p $en $en.Size { param($buf, $n) $script:smallBuf.Write($buf, 0, $n) }
                    Dump-Small $innerRel $script:smallBuf.ToArray()
                }
                if ($fmt -eq 'PE/MZ executable' -or $fmt -like 'X360 executable*') {
                    $exes.Add([pscustomobject]@{ Full = $outPath; Rel = $innerRel; Kind = $(if ($fmt -like 'X360*') { 'XEX' } else { 'PE' }) })
                }
            } catch {
                $errors.Add("$innerRel : $($_.Exception.Message)")
            }
        }
        Write-Progress -Id 1 -Activity "Reading package $rel" -Completed
    } finally { $p.Fs.Dispose() }
}

for ($idx = 0; $idx -lt $total; $idx++) {
    $f = $files[$idx]
    $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/')
    if (($idx % 25) -eq 0) {
        Write-Progress -Activity "Scanning $safeLabel" -Status "$idx / $total  $rel" -PercentComplete ([int](100 * $idx / [Math]::Max(1, $total)))
    }
    try {
        $head = Read-Head $f.FullName $headLen
        $hash = ''
        if (-not $SkipHash) { $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash }
        $fmt = Add-Row $rel $f.Extension $f.Length $hash $head
        if ($smallExts -contains $f.Extension.ToLowerInvariant() -and $f.Length -le $smallMax -and $rel -notmatch '^Support[\\/]') {
            Dump-Small $rel ([System.IO.File]::ReadAllBytes($f.FullName))
        }
        if ($fmt -like 'X360 STFS*') {
            $stfsCount++
            Write-Host "Reading Xbox 360 package $rel"
            try { Scan-Package $f.FullName $rel }
            catch { $pkgLines.Add("  (error reading package: $($_.Exception.Message))"); $errors.Add("$rel : $($_.Exception.Message)") }
        }
        elseif ($fmt -like 'EA BIG archive (BIGH)') {
            $bigCount++
            Write-Host "Reading archive $rel"
            try { Scan-Big $f.FullName $rel }
            catch { $bigLines.Add("  (error reading archive: $($_.Exception.Message))"); $errors.Add("$rel : $($_.Exception.Message)") }
        }
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
function Top-Folder([string]$rel) {
    $i = $rel.IndexOf('::')
    if ($i -ge 0) { return $rel.Substring(0, $i) + ' (contents)' }
    return ($rel -split '[\\/]')[0]
}
$sum = New-Object System.Collections.Generic.List[string]
$diskBytes = [int64]0
foreach ($f in $files) { $diskBytes += $f.Length }
$sum.Add("DS2 file scan: $safeLabel")
$sum.Add(('Scanned folder : {0}' -f (Split-Path $root -Leaf)))
$sum.Add(('Scan date      : {0:yyyy-MM-dd HH:mm} (local)' -f (Get-Date)))
$sum.Add(('PowerShell     : {0}' -f $PSVersionTable.PSVersion))
$sum.Add(('Files on disk  : {0} ({1:N0} bytes, {2:N2} GB)' -f $files.Count, $diskBytes, ($diskBytes / 1GB)))
$sum.Add(('Containers     : {0} Xbox 360 package(s), {1} BIGH archive(s); {2} files inside them (listed as container::path or container::#hash)' -f $stfsCount, $bigCount, ($rows.Count - $files.Count)))
$sum.Add(('Hashes         : {0}' -f $(if ($SkipHash) { 'skipped' } else { 'SHA-256' })))
$sum.Add(('Extracted to   : {0}' -f $(if ($ExtractTo) { 'yes (folder not recorded)' } else { 'no' })))
$sum.Add(('Elapsed        : {0:N0} s' -f $sw.Elapsed.TotalSeconds))
$sum.Add('')
$sum.Add('Top-level folders:')
foreach ($g in ($rows | Group-Object { Top-Folder $_.RelativePath } | Sort-Object Name)) {
    $sz = ($g.Group | Measure-Object Size -Sum).Sum
    $sum.Add(('  {0,-60} {1,8} files {2,18:N0} bytes' -f $g.Name, $g.Count, $sz))
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
        $b = $heads[$r.RelativePath]
        if ($b.Length -gt $SampleBytes) { $t = New-Object byte[] $SampleBytes; [Array]::Copy($b, $t, $SampleBytes); $b = $t }
        foreach ($l in (Hex-Dump $b)) { $smp.Add($l) }
    }
}
$smp | Set-Content -LiteralPath (Join-Path $dest 'samples.txt') -Encoding UTF8

# archives.txt
$bigLines.Insert(0, "EA BIGH archives - $safeLabel ($bigCount found). Entries appear in manifest.csv as <archive>::#<name hash>.")
$bigLines | Set-Content -LiteralPath (Join-Path $dest 'archives.txt') -Encoding UTF8

# smallfiles.txt
$smallLines.Insert(0, "Small descriptor/config files, full contents - $safeLabel")
$smallLines | Set-Content -LiteralPath (Join-Path $dest 'smallfiles.txt') -Encoding UTF8

# packages.txt
$pkgLines.Insert(0, "Xbox 360 STFS packages - $safeLabel ($stfsCount found)")
$pkgLines | Set-Content -LiteralPath (Join-Path $dest 'packages.txt') -Encoding UTF8

# executables.txt
$exe = New-Object System.Collections.Generic.List[string]
$exe.Add("Executables - $safeLabel ($($exes.Count) found)")
$exe.Add("String filter: $keywordPattern")
foreach ($x in $exes) {
    $exe.Add('')
    if (-not $x.Full) { $exe.Add("== $($x.Rel)  [$($x.Kind)]  (inside a package - rerun with -ExtractTo to analyse it)"); continue }
    Write-Host "Inspecting $($x.Rel)"
    try { foreach ($l in (Describe-Executable $x.Full $x.Rel $x.Kind)) { $exe.Add($l) } }
    catch { $exe.Add("== $($x.Rel)  (error: $($_.Exception.Message))") }
}
$exe | Set-Content -LiteralPath (Join-Path $dest 'executables.txt') -Encoding UTF8

Write-Host ''
Write-Host "Done in $([int]$sw.Elapsed.TotalSeconds) s. $($files.Count) files on disk, $stfsCount Xbox 360 package(s), $bigCount BIGH archive(s), $($rows.Count - $files.Count) files inside them, $($exes.Count) executables."
Write-Host "Results: $dest"
if ($ExtractTo) { Write-Host "Package contents extracted to: $ExtractTo" }
if ($errors.Count -gt 0) { Write-Warning "$($errors.Count) files could not be read; see summary.txt" }
