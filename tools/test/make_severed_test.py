r"""First in-game test of the converted Severed files.

Builds DS2DAT2.DAT in the Dead Space 2 folder from your own Severed addon
file:
  - every Severed file converted to the PC formats, at its own path;
  - the PC's own global_assets\global_assets_global.str with Severed's
    updated Lua audio scripts swapped in.
Severed is then started from the episode select screen: the probe DLL
(tools/probe, v7) adds its entry when F9 is pressed on the title screen.
With --hijack-ch01 (older test) New Game loads Severed in place of
chapter 1 instead (Severed's TOCs and stream list under chapter 1's and
the ds_2 episode's names, chapter 1's stream sets blanked, level list
entry patched).
Nothing else is changed; remove it with --remove (the game is normal
again). Never overwrites an archive it did not create (marker file
DS2DAT2.DAT.severedtest next to it).

    py -3 make_severed_test.py --severed <addon file> --game "<Dead Space 2 folder>" [--ffmpeg <ffmpeg.exe>] [--work <folder>]
    py -3 make_severed_test.py --game "<Dead Space 2 folder>" --remove
"""
import argparse, glob, os, shutil, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'research'))

try:
    from ds2 import bigarchive, build, eaaudio, simgroup, stfs, streamfile, streamwrite, toc   # noqa: E402
except ImportError:
    raise SystemExit('Run this from the repository\'s tools\\test folder: it needs tools\\research next to it '
                     '(copy the whole repository, not just this file).')

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


def strip_dropped(dst):
    """remove asset types the PC cannot load (build.DROP) from streams
    converted by an earlier version, fixing the TOC sizes"""
    changed = {}
    for d, _, fs in os.walk(dst):
        for f in fs:
            if not f.lower().endswith('.str'):
                continue
            p = os.path.join(d, f)
            data = open(p, 'rb').read()
            if not any(t.encode() in data for t in build.DROP):
                continue
            _, assets = streamfile.read(data)
            if not any(a.type in build.DROP for a in assets):
                continue
            w = streamwrite.Writer()
            total = 0
            for a in assets:
                if a.type in build.DROP:
                    log('  leaving out %s %s' % (a.type, a.name))
                    continue
                y = a.payload()
                w.add(a.type_hash, a.flags, a.ids, a.name, a.path, a.type, y)
                total += len(y)
            open(p, 'wb').write(w.data())
            changed[os.path.splitext(os.path.relpath(p, dst))[0].replace('/', '\\')] = total
    if changed:
        for d, _, fs in os.walk(dst):
            for f in fs:
                if f.lower().endswith('.toc'):
                    p = os.path.join(d, f)
                    y = open(p, 'rb').read()
                    for name, size in changed.items():
                        y = toc.set_size(y, name, size)
                    open(p, 'wb').write(y)


def refresh_simgroups(root, dst, class_hash):
    """re-convert the SimGroups of streams that use a class whose layout was
    added to the schema after the files were converted"""
    key = struct.pack('<I', class_hash)
    for d, _, fs in os.walk(dst):
        for f in fs:
            if not f.lower().endswith('.str'):
                continue
            p = os.path.join(d, f)
            data = open(p, 'rb').read()
            if key not in data:
                continue
            _, assets = streamfile.read(data)
            if not any(a.type == 'SimGroup' and key in a.payload() for a in assets):
                continue
            src = os.path.join(root, os.path.relpath(p, dst))
            if not os.path.exists(src):
                continue
            fresh = {(a.name, a.ids): a for a in streamfile.read(open(src, 'rb').read())[1] if a.type == 'SimGroup'}
            w = streamwrite.Writer()
            n = 0
            for a in assets:
                y = a.payload()
                if a.type == 'SimGroup' and (a.name, a.ids) in fresh:
                    z = simgroup.convert(fresh[(a.name, a.ids)].payload())
                    if z is not None and len(z) == len(y):
                        y, n = z, n + 1
                w.add(a.type_hash, a.flags, a.ids, a.name, a.path, a.type, y)
            open(p, 'wb').write(w.data())
            log('  re-converted %d SimGroup(s) in %s' % (n, os.path.relpath(p, dst)))


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
    ap.add_argument('--hijack-ch01', action='store_true',
                    help='older test: New Game loads Severed in place of chapter 1')
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
    a.severed = os.path.abspath(a.severed.rstrip('\\/"'))
    work = a.work or os.path.join(os.path.dirname(a.severed), 'severed_work')
    src, dst = os.path.join(work, '360'), os.path.join(work, 'pc')

    log('Indexing the game archives')
    idx, trailer = game_index(a.game)
    for h in (LEVEL_LIST, bigarchive.name_hash('global_assets\\global_assets_global.str')):
        if h not in idx:
            raise SystemExit('Expected file #%08X not found in the game archives' % h)

    if os.path.isdir(a.severed):
        src = a.severed                      # already extracted from the package
        log('Using the extracted Severed folder', src)
    elif not os.path.exists(os.path.join(work, 'unpacked.ok')):
        log('Unpacking the Severed package')
        pkg = stfs.Package(open(a.severed, 'rb').read())
        for path, data in pkg.files():
            q = os.path.join(src, *path.replace('\\', '/').split('/'))
            os.makedirs(os.path.dirname(q), exist_ok=True)
            open(q, 'wb').write(data)
        open(os.path.join(work, 'unpacked.ok'), 'w').write('ok')
    root = src.rstrip('\\/')
    while len(os.listdir(root)) == 1 and os.path.isdir(os.path.join(root, os.listdir(root)[0])):
        root = os.path.join(root, os.listdir(root)[0])          # the package's own top folder

    left_out = {}
    if not os.path.exists(os.path.join(work, 'converted.ok')):
        log('Converting (this takes a while: about an hour)')
        report = build.build(root, dst, log=log)
        left_out = {k: v for k, v in report.items() if not k.startswith(('converted', 'dropped'))}
        for k, v in sorted(report.items()):
            log('  %-45s %d' % (k, len(v)))
            if not k.startswith(('converted', 'dropped')):
                for n in v[:10]:
                    log('      ' + n)
        open(os.path.join(work, 'converted.ok'), 'w').write('ok')
    else:
        log('Using the files converted by an earlier run (delete %s to convert again)' % os.path.join(work, 'converted.ok'))

    strip_dropped(dst)
    if not os.path.exists(os.path.join(work, 'uniform_fix.ok')):
        refresh_simgroups(root, dst, 0x0575C2F4)       # Uniform layout added (probe 15)
        open(os.path.join(work, 'uniform_fix.ok'), 'w').write('ok')
    if not os.path.exists(os.path.join(work, 'neutral_fix.ok')):
        for h in sorted(simgroup.NEUTRAL):               # Severed-only classes -> blank NavFolder
            refresh_simgroups(root, dst, h)
        open(os.path.join(work, 'neutral_fix.ok'), 'w').write('ok')
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
    # Experiment (probe 12): the level's SimGroup, which holds Severed's
    # StreamSet and checkpoint objects, also as a stream sets file, requested
    # in stream-sets mode by the probe like the base chapters' ones.
    main = os.path.join(dst, 'pdlc1_ch01_mng', 'pdlc1_ch01_mng.str')
    if os.path.exists(main):
        w = streamwrite.Writer()
        for x in streamfile.read(open(main, 'rb').read())[1]:
            if x.type == 'SimGroup':
                w.add(x.type_hash, x.flags, x.ids, x.name, x.path, x.type, x.payload())
        files.append(('pdlc1_ch01_mng\\pdlc1_ch01_mng_streamsets.str', w.data()))
        log('  pdlc1_ch01_mng_streamsets.str: the level SimGroup as a stream sets file')
    extra, raw = [], {}
    if a.hijack_ch01:
        lvl = patched_level_list(read_entry(idx, LEVEL_LIST))
        toc_dir = os.path.join(dst, 'pdlc1_ch01_mng')
        files.append(('ch01_hos\\ch01_hos.toc', os.path.join(toc_dir, 'pdlc1_ch01_mng.toc')))
        files.append(('ch01_hos\\ch01_hos_global.toc', os.path.join(toc_dir, 'pdlc1_ch01_mng_global.toc')))
        # Severed has no stream sets file (the console DLC loads without one);
        # chapter 1's would stream chapter 1's own sections, so blank it.
        files.append(('ch01_hos\\ch01_hos_streamsets.str', streamwrite.Writer().data()))
        # The PC's chapter 1 entry (built into the exe) uses the episode folder
        # ds_2\ with stream list ds_2.str; Severed's entry uses its own
        # pdlc1_ch01_mng\pdlc1_ch01_mng.str. Put Severed's under the ds_2 names.
        for n in ('.toc', '_global.toc', '.str', '_global.str'):
            files.append(('ds_2\\ds_2' + n, os.path.join(toc_dir, 'pdlc1_ch01_mng' + n)))
        extra, raw = [('#level list', lvl)], {'#level list': LEVEL_LIST}

    log('Writing', target)
    tmp = target + '.tmp'
    names = bigarchive.write(tmp, files + extra, trailer, raw=raw)
    os.replace(tmp, target)
    open(marker, 'w').write('Severed test archive created by tools/test/make_severed_test.py. Remove with --remove.')
    log('Done: %d files in %s (%.1f GB)' % (len(names), target, os.path.getsize(target) / 1e9))
    if left_out:
        log('Some files were left out; please send me this window\'s text.')


if __name__ == '__main__':
    main()
