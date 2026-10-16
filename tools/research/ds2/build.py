"""Converts Severed's 360 files into PC files.

    python3 -m ds2.build <severed dir> <out dir>

Stream files (.str) are converted asset by asset (convert.py and the mesh,
volatile and VFX models) and written in the PC layout (streamwrite.py);
tables of contents get their byte order and the new stream sizes
(toc.py); audio streams (.snu) are re-encoded (snu.py). Text and other
platform-neutral files are copied. A report lists any asset that could not
be converted (it is left out of the PC stream).
"""
import os, pickle, struct, sys, collections
from . import streamfile, streamwrite, convert, toc, nav, geo, meshconv, templates as T, vfx, lut

HERE = os.path.dirname(__file__)
_MODELS = {}


def _model(name):
    if name not in _MODELS:
        _MODELS[name] = pickle.load(open(os.path.join(HERE, name), 'rb'))
    return _MODELS[name]


def _vfx(x):
    tm = _model('vfx_templates.pkl')
    out = bytearray()
    for key, s, e in vfx.segments(x):
        t = tm.get(key)
        if t is None:
            return None
        out += T.apply(t[0], x[s:e])
    return bytes(out)


def _volatile(g, x):
    from . import volslots
    return volslots.convert(_model('volatile_table.pkl'), g, x)


# asset types the PC engine has no handler for; registering one crashes the
# game (null type info), and they are not needed on PC
DROP = {'PNG': 'Xbox 360 save game icons'}


def convert_stream(data, report):
    """360 stream bytes -> (PC stream bytes, total uncompressed size)"""
    _, assets = streamfile.read(data)
    w = streamwrite.Writer()
    total = 0
    mesh = None                       # a MeshVolatile follows its Mesh
    luts = set()                      # LUT textures: header, then data (ds2/lut.py)
    for a in assets:
        if a.type in DROP:
            report['dropped: %s (%s)' % (a.type, DROP[a.type])].append(a.name)
            continue
        x = a.payload()
        name, ids = a.name, a.ids
        try:
            if a.type == 'tg4h' and lut.is_lut_header(x):
                y = lut.header(x)
                luts.add(a.name)
            elif a.type == 'tg4d' and a.name in luts:
                y = lut.data(x)               # D3D byte order; the test build re-checks it against the PC
            elif a.type == 'Mesh':
                y = meshconv.convert(x, _model('mesh_templates.pkl'))
                mesh = geo.parse(x, True)
            elif a.type == 'MeshVolatile':
                y = _volatile(mesh, x) if mesh is not None else None
            elif a.type == 'VFX':
                y = _vfx(x)
            elif a.type in convert.CONVERTERS:
                y = convert.CONVERTERS[a.type](x)
                if a.type == 'NAV':
                    name, ids = nav.pc_name(a.name), nav.pc_ids(a.name, a.ids)
            else:
                y = None
        except Exception as e:                # noqa: BLE001 - reported below
            report['error %s: %s' % (a.type, type(e).__name__)].append(a.name)
            continue
        if y is None:
            report['not converted: ' + a.type].append(a.name)
            continue
        report['converted: ' + a.type].append(a.name)
        w.add_asset(a, y, name=name, ids=ids)
        total += len(y)
    return w.data(), total


COPY = {'.lds', '.key', '.pid', '.lvl', '.dlm', '.add', '.bin', '.vp6'}


def build(src, dst, log=print):
    report = collections.defaultdict(list)
    sizes = {}
    tocs = []
    for d, _, files in os.walk(src):
        for f in sorted(files):
            p = os.path.join(d, f)
            rel = os.path.relpath(p, src)
            q = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(q), exist_ok=True)
            ext = os.path.splitext(f)[1].lower()
            if ext == '.str':
                out, total = convert_stream(open(p, 'rb').read(), report)
                open(q, 'wb').write(out)
                sizes[os.path.splitext(rel)[0].replace('/', '\\').lower()] = total
                log('stream %s: %d bytes' % (rel, len(out)))
            elif ext == '.toc':
                tocs.append((p, q))
            elif ext == '.snu':
                if os.path.exists(q) and os.path.getsize(q):
                    continue                      # converted by an earlier run
                from . import snu
                y = snu.convert(open(p, 'rb').read())
                if y is None:
                    report['not converted: snu'].append(rel)
                else:
                    open(q, 'wb').write(y)
            elif ext in COPY:
                open(q, 'wb').write(open(p, 'rb').read())
            else:
                report['unknown file'].append(rel)
    for p, q in tocs:
        x = open(p, 'rb').read()
        names = toc.parse(x)['stream_names']
        known = {n: sizes[n.lower()] for n in names if n.lower() in sizes}
        open(q, 'wb').write(toc.convert(x, known))
        if len(known) != len(names):
            report['toc streams without a converted .str'].extend(n for n in names if n.lower() not in sizes)
    return report


if __name__ == '__main__':
    r = build(sys.argv[1], sys.argv[2])
    for k in sorted(r):
        print('%-50s %d' % (k, len(r[k])))
        if not k.startswith(('converted', 'dropped')):
            for n in r[k][:20]:
                print('    ', n)
