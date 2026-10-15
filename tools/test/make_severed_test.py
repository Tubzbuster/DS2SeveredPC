"""First in-game test of the converted Severed files.

Builds DS2DAT2.DAT in the Dead Space 2 folder from your own Severed addon
file:
  - every Severed file converted to the PC formats, at its own path;
  - the game's level list with the chapter 1 entry ('ch01_hos') pointing
    at Severed's level (folder, stream list, checkpoints), and Severed's
    TOCs also under chapter 1's TOC names, so New Game should start
    Severed;
  - the PC's own global_assets\\global_assets_global.str with Severed's
    updated Lua audio scripts swapped in.
Nothing else is changed; remove it with --remove (the game is normal
again). Never overwrites an archive it did not create (marker file
DS2DAT2.DAT.severedtest next to it).

    py -3 make_severed_test.py --severed <addon file> --game "<Dead Space 2 folder>" [--ffmpeg <ffmpeg.exe>] [--work <folder>]
    py -3 make_severed_test.py --game "<Dead Space 2 folder>" --remove
"""
import argparse, glob, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'research'))

from ds2 import bigarchive, build, eaaudio, stfs, streamfile, streamwrite   # noqa: E402

LEVEL_LIST = 0xE4529CFE        # level list (text), identical on PC and 360
SLOT = 'DS2DAT2.DAT'


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def game_index(game):
    """{hash: (archive path, offset, size)} over the game's own archives, and a trailer"""
    idx, trailer = {}, None
    for p in sorted(glob.glob(os.path.join(game, 'DS2DAT*.DAT'))):
        if os.path.basename(p).upper() == SLOT:
            continue
        with open(p, 'rb') as f:
            i, t = bigarchive.read_index(f)
        trailer = trailer or t
        for h, (o, s) in i.items():
            idx.setdefault(h, (p, o, s))
    return idx, trailer or bytes(8)


def read_entry(idx, h):
    p, o, s = idx[h]
    with open(p, 'rb') as f:
        f.seek(o)
        return f.read(s)


def patched_level_list(text):
    lines = text.split(b'\n')
    sev = [l for l in lines if l.startswith(b'pdlc1_ch01_mng ')]
    if not sev:
        raise SystemExit('Severed is not in the level list (unexpected game version)')
    out = [b'ch01_hos ' + sev[0][len(b'pdlc1_ch01_mng '):] if l.startswith(b'ch01_hos ') else l for l in lines]
    return b'\n'.join(out)


def patched_global_assets(pc, sev):
    """the PC's stream with its Lua assets replaced by Severed's (same names)"""
    _, pa = streamfile.read(pc)
    _, sa = streamfile.read(sev)
    lua = {(a.type, a.name): a for a in sa if a.type == 'LUA'}
    w = streamwrite.Writer()
    swapped = 0
    for a in pa:
        s = lua.get((a.type, a.name))
        if s is not None:
            swapped += 1
        src = s or a
        w.add(src.type_hash, src.flags, src.ids, src.name, src.path, src.type, src.payload())
    return w.data(), swapped, len(lua)


def remove(game):
    target = os.path.join(game, SLOT)
    marker = target + '.severedtest'
    if not os.path.exists(target):
        log('Nothing to remove:', target, 'does not exist.')
        return
    if not os.path.exists(marker):
        raise SystemExit(target + ' was not created by this script; not touching it.')
    os.remove(target)
    os.remove(marker)
    log('Removed', target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', required=True)
    ap.add_argument('--severed')
    ap.add_argument('--ffmpeg', default='ffmpeg')
    ap.add_argument('--work', default=None)
    ap.add_argument('--remove', action='store_true')
    a = ap.parse_args()
    if a.remove:
        return remove(a.game)
    if not a.severed:
        raise SystemExit('--severed <addon file> is needed')
    target = os.path.join(a.game, SLOT)
    marker = target + '.severedtest'
    if os.path.exists(target) and not os.path.exists(marker):
        raise SystemExit(target + ' already exists and was not created by this script; not overwriting it.')
    eaaudio.FFMPEG = a.ffmpeg
    work = a.work or os.path.join(os.path.dirname(os.path.abspath(a.severed)), 'severed_work')
    src, dst = os.path.join(work, '360'), os.path.join(work, 'pc')

    log('Indexing the game archives')
    idx, trailer = game_index(a.game)
    for h in (LEVEL_LIST, bigarchive.name_hash('global_assets\\global_assets_global.str')):
        if h not in idx:
            raise SystemExit('Expected file #%08X not found in the game archives' % h)

    if not os.path.exists(os.path.join(work, 'unpacked.ok')):
        log('Unpacking the Severed package')
        pkg = stfs.Package(open(a.severed, 'rb').read())
        for path, data in pkg.files():
            q = os.path.join(src, *path.replace('\\', '/').split('/'))
            os.makedirs(os.path.dirname(q), exist_ok=True)
            open(q, 'wb').write(data)
        open(os.path.join(work, 'unpacked.ok'), 'w').write('ok')
    root = src
    while len(os.listdir(root)) == 1 and os.path.isdir(os.path.join(root, os.listdir(root)[0])):
        root = os.path.join(root, os.listdir(root)[0])          # the package's own top folder

    left_out = {}
    if not os.path.exists(os.path.join(work, 'converted.ok')):
        log('Converting (this takes a while: about an hour)')
        report = build.build(root, dst, log=log)
        left_out = {k: v for k, v in report.items() if not k.startswith('converted')}
        for k, v in sorted(report.items()):
            log('  %-45s %d' % (k, len(v)))
            if not k.startswith('converted'):
                for n in v[:10]:
                    log('      ' + n)
        open(os.path.join(work, 'converted.ok'), 'w').write('ok')
    else:
        log('Using the files converted by an earlier run (delete %s to convert again)' % os.path.join(work, 'converted.ok'))

    log('Preparing the test entries')
    files = []
    for d, _, fs in os.walk(dst):
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, dst).replace('/', '\\')
            if rel.lower() == 'global_assets\\global_assets_global.str':
                continue
            files.append((rel, p))
    pc_ga = read_entry(idx, bigarchive.name_hash('global_assets\\global_assets_global.str'))
    ga, swapped, total = patched_global_assets(pc_ga, open(os.path.join(dst, 'global_assets', 'global_assets_global.str'), 'rb').read())
    log('  global_assets_global.str: %d of %d Severed Lua scripts swapped in' % (swapped, total))
    files.append(('global_assets\\global_assets_global.str', ga))
    lvl = patched_level_list(read_entry(idx, LEVEL_LIST))
    toc_dir = os.path.join(dst, 'pdlc1_ch01_mng')
    files.append(('ch01_hos\\ch01_hos.toc', os.path.join(toc_dir, 'pdlc1_ch01_mng.toc')))
    files.append(('ch01_hos\\ch01_hos_global.toc', os.path.join(toc_dir, 'pdlc1_ch01_mng_global.toc')))

    log('Writing', target)
    tmp = target + '.tmp'
    names = bigarchive.write(tmp, files + [('#level list', lvl)], trailer, raw={'#level list': LEVEL_LIST})
    os.replace(tmp, target)
    open(marker, 'w').write('Severed test archive created by tools/test/make_severed_test.py. Remove with --remove.')
    log('Done: %d files in %s (%.1f GB)' % (len(names), target, os.path.getsize(target) / 1e9))
    if left_out:
        log('Some files were left out; please send me this window\'s text.')


if __name__ == '__main__':
    main()
