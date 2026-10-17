"""Save pictures and titles for Severed's saves (PC load menu).

The PC load menu picks a save's picture and title by its chapter number
only (exe 0xBAE170): the key "ch%02d" (sdbm hash) is looked up in the
UIMenuCheckpointIcons table (global_assets SimGroup) for a picture VFX,
and "CH%02d_TitleString" in the string tables for the title. Severed sets
chapters 1 and 2 (PlayerSetChapter), so its saves showed the base game's
chapter 1/2 picture and title. The converter numbers both of Severed's
chapters 16 (simgroup.CHAPTERS) and this module adds, to the PC's own
streams:

- a texture ui_saveload_icn_ch16 (DXT5 128x64, 3 mips, as the base
  pictures) made from Severed's 64x64 Xbox save icon weller1_ch1.png,
  stretched;
- a picture VFX, a copy of ui_saveload_icn01.vfx naming that texture;
- the table's placeholder entry "ch00" (chapter 1's picture; the save list
  only ever asks for ch01-ch15) renamed ch16 and pointed at the new VFX
  (GUID appended, see _table);
- CH16_TitleString ("Severed", replacing the unused base "Chapter 16") in
  each language's global string table.

Asset ids: textures (type hash, 0, type hash, crc32(folder),
crc32(folder + name)); VFX (type hash, g, g, g, g2) where g is the sdbm hash
of the source path (g2: see _guid) and the table's GUID is g, g, g, g2.

The string tables are in DS2DAT0.DAT, which wins over the test archive
(the lowest-numbered archive holding a file is used), so the title stays
the base "Chapter 16" for now.
"""
import struct
import zlib

NEW = {16: 1}                  # PC chapter -> Severed icon (weller1_ch<n>)
SLOTS = {16: 'ch00'}
TEMPLATE_VFX = 'ui_saveload_icn01.vfx'
TEMPLATE_TEX = 'ui_saveload_icn_ch01'
TEX_FOLDER = b'shared_vfx_textures_ui_textures_frontend_icons'
VFX_SRC = 's:\\assets\\shared\\vfx\\player_ui\\frontend\\icons\\ui_saveload_icn%02d.vfx'
TABLE_PATH = 'levels\\global_assets\\global_assets\\streams\\global_assets.simgroup.bin'
TITLE = 'Severed'              # the DLC's name, the same in every language
TAG_HASH, TAG_GUID = 0xFF0AFFFF, 0xFF0CFFFF


def sdbm(s):
    h = 0
    for c in s.lower().encode('latin1'):
        h = (h * 65599 + c) & 0xFFFFFFFF
    return h


# ---- PNG (8-bit RGB/RGBA, non-interlaced) -------------------------------

def png_rgba(b):
    assert b[:8] == b'\x89PNG\r\n\x1a\n'
    o, idat = 8, b''
    while o + 8 <= len(b):
        n, t = struct.unpack_from('>I4s', b, o)
        if t == b'IEND':
            break
        c = b[o + 8:o + 8 + n]
        if t == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', c)
            assert depth == 8 and ctype in (2, 6) and not inter
        elif t == b'IDAT':
            idat += c
        o += 12 + n
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            up = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + up) & 255
            elif f == 3:
                line[i] = (line[i] + (a + up) // 2) & 255
            elif f == 4:
                p = a + up - c
                pa, pb, pc = abs(p - a), abs(p - up), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else up if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    px = [[tuple(r[x * bpp:x * bpp + 3]) + ((r[x * bpp + 3],) if bpp == 4 else (255,)) for x in range(w)] for r in rows]
    return w, h, px


def resize(px, w, h, nw, nh):
    """bilinear"""
    out = []
    for y in range(nh):
        fy = max(0.0, (y + 0.5) * h / nh - 0.5)
        y0 = min(int(fy), h - 1)
        y1, ty = min(y0 + 1, h - 1), fy - int(fy)
        row = []
        for x in range(nw):
            fx = max(0.0, (x + 0.5) * w / nw - 0.5)
            x0 = min(int(fx), w - 1)
            x1, tx = min(x0 + 1, w - 1), fx - int(fx)
            row.append(tuple(int(round(px[y0][x0][k] * (1 - tx) * (1 - ty) + px[y0][x1][k] * tx * (1 - ty) +
                                       px[y1][x0][k] * (1 - tx) * ty + px[y1][x1][k] * tx * ty)) for k in range(4)))
        out.append(row)
    return out


# ---- DXT5 -----------------------------------------------------------------

def _565(c):
    return ((c[0] >> 3) << 11) | ((c[1] >> 2) << 5) | (c[2] >> 3)


def _rgb(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _dxt5_block(blk):
    alphas = [p[3] for p in blk]
    a0, a1 = max(alphas), min(alphas)
    if a0 == a1:
        ab = bytes([a0, a1]) + bytes(6)
    else:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
        bits = 0
        for i, a in enumerate(alphas):
            bits |= min(range(8), key=lambda k: abs(pal[k] - a)) << (3 * i)
        ab = bytes([a0, a1]) + bits.to_bytes(6, 'little')
    # colour endpoints: the two pixels furthest apart along the luminance-ish axis
    lum = [p[0] * 2 + p[1] * 3 + p[2] for p in blk]
    hi, lo = blk[lum.index(max(lum))], blk[lum.index(min(lum))]
    c0, c1 = _565(hi), _565(lo)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return ab + struct.pack('<HHI', c0, c1, 0)
    e0, e1 = _rgb(c0), _rgb(c1)
    pal = [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1)), tuple((a + 2 * b) // 3 for a, b in zip(e0, e1))]
    bits = 0
    for i, p in enumerate(blk):
        bits |= min(range(4), key=lambda k: sum((pal[k][j] - p[j]) ** 2 for j in range(3))) << (2 * i)
    return ab + struct.pack('<HHI', c0, c1, bits)


def dxt5(px, w, h):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            out += _dxt5_block([px[min(by + y, h - 1)][min(bx + x, w - 1)] for y in range(4) for x in range(4)])
    return bytes(out)


def texture_data(png, w=128, h=64, mips=3):
    sw, sh, px = png_rgba(png)
    out = b''
    for m in range(mips):
        mw, mh = max(4, w >> m), max(4, h >> m)
        out += dxt5(resize(px, sw, sh, mw, mh), mw, mh)
    return out


# ---- assets ---------------------------------------------------------------

# The GUID's last word: not reproduced from any name hash tried, but along
# the base pictures it grows by exactly 0x3F17455 / 4 per chapter within each
# tens group (icn10-icn15: ((4 * 0xF6D5894C + 1) + n * 0x3F17455) >> 2, 34-bit),
# which gives icn16 0xFCBFB7CB. (The first version used a crc32, which
# matches none of the base pictures: the picture came out blank.)
G2_TENS = (4 * 0xF6D5894C + 1, 0x3F17455)


def _guid(ch):
    g = sdbm(VFX_SRC % ch)
    base, step = G2_TENS
    assert 10 <= ch <= 19
    return (g, g, g, ((base + (ch - 10) * step) % (1 << 34)) >> 2)


def _table(p, stats):
    """rename the placeholder entries and point them at the new VFX. The
    table's GUID fields are offsets into a pool of GUIDs shared between
    entries (ch00, default and ch01 share one), so the new GUIDs are
    appended to the SimGroup and the block size (its header word +4 at
    [0x04], running to the end of the file) grows to cover them."""
    out = bytearray(p)
    block = struct.unpack_from('<I', out, 4)[0]
    if struct.unpack_from('<I', out, block)[0] != 0x91C8773C or block + struct.unpack_from('<I', out, block + 4)[0] != len(out):
        stats['table_layout_unknown'] = 1
        return p
    for ch, slot in SLOTS.items():
        key = struct.pack('<II', TAG_HASH, sdbm(slot))
        i = out.find(key)
        if i < 0 or struct.unpack_from('<I', out, i + 12)[0] != TAG_GUID:
            stats['table_missing_' + slot] = 1
            continue
        struct.pack_into('<I', out, i + 4, sdbm('ch%02d' % ch))
        out += bytes(-len(out) % 4)
        g = len(out)
        out += struct.pack('<4I', *_guid(ch))
        struct.pack_into('<I', out, i + 16, g - (i + 16))         # the GUID entry (at i + 8): {field hash, tag, offset from +8}
        stats['table_entries'] = stats.get('table_entries', 0) + 1
    struct.pack_into('<I', out, block + 4, len(out) - block)
    return bytes(out)


def _vfx(p, ch):
    old = TEMPLATE_VFX.split('.')[0][-5:].encode()                # icn01
    y = p.replace(old, b'icn%02d' % ch).replace(b'cn_ch01', b'cn_ch%02d' % ch)
    assert len(y) == len(p)
    return y


def _lh2(p, stats):
    n, L = struct.unpack_from('<II', p, 0x10)
    if p[:4] != b'LCH2' or L != 1:
        return p
    ids = list(struct.unpack_from('<%dI' % n, p, 0x20))
    offs = struct.unpack_from('<%dI' % n, p, 0x20 + 4 * n)
    text = {i: p[o:p.index(b'\0', o)] for i, o in zip(ids, offs)}
    for ch in NEW:
        text[sdbm('CH%02d_TitleString' % ch)] = TITLE.encode('utf-8')
    ids = sorted(text)
    head = 0x20 + 8 * len(ids)
    body, offs = bytearray(), []
    for i in ids:
        offs.append(head + len(body))
        body += text[i] + b'\0'
    out = bytearray(p[:0x20]) + struct.pack('<%dI' % len(ids), *ids) + struct.pack('<%dI' % len(ids), *offs) + body
    struct.pack_into('<I', out, 4, len(out))
    struct.pack_into('<I', out, 0x10, len(ids))
    stats['titles'] = stats.get('titles', 0) + 1
    return bytes(out)


def patch(assets, icons, stats):
    """assets: one PC stream's assets (streamfile); icons: {Severed chapter:
    PNG bytes}. Returns [(type_hash, flags, ids, name, path, type, payload)]
    or None if nothing in the stream is concerned."""
    out, hit = [], False
    for a in assets:
        y = a.payload()
        if a.type == 'SimGroup' and a.path.lower() == TABLE_PATH:
            y, hit = _table(y, stats), True
        elif a.type == 'LH2' and a.name.lower().startswith('deadspace2_global.'):
            y, hit = _lh2(y, stats), True
        out.append([a.type_hash, a.flags, a.ids, a.name, a.path, a.type, y])
        if a.type == 'VFX' and a.name == TEMPLATE_VFX:
            for ch in NEW:
                out.append([a.type_hash, a.flags, (a.ids[0],) + _guid(ch), a.name.replace('01', '%02d' % ch),
                            a.path.replace('icn01', 'icn%02d' % ch), a.type, _vfx(y, ch)])
            hit = True
            stats['vfx'] = stats.get('vfx', 0) + len(NEW)
        elif a.type in ('tg4h', 'tg4d') and a.name == TEMPLATE_TEX and NEW[16] in icons:
            for ch, sev in NEW.items():
                name = TEMPLATE_TEX.replace('ch01', 'ch%02d' % ch)
                ids = a.ids[:4] + (zlib.crc32(name.encode(), zlib.crc32(TEX_FOLDER)),)
                if a.type == 'tg4h':
                    z = y.replace(TEMPLATE_TEX.encode(), name.encode())
                else:
                    z = texture_data(icons[sev])
                    if len(z) != len(y):
                        stats['texture_size_mismatch'] = len(y)
                        continue
                out.append([a.type_hash, a.flags, ids, name, a.path.replace('ch01', 'ch%02d' % ch), a.type, z])
                stats[a.type] = stats.get(a.type, 0) + 1
            hit = True
    return out if hit else None
