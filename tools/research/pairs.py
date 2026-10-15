"""Load the exported PC/360 asset pairs (tools/export output) keyed by
(type, name, ids)."""
import sys
from ds2 import streamfile

_cache = {}


def load(export_dir):
    if export_dir in _cache:
        return _cache[export_dir]
    out = {}
    for plat, f in (('pc', 'pc_assets.str'), ('x', 'x360_assets.str')):
        be, assets = streamfile.read(open(export_dir + '/' + f, 'rb').read())
        out[plat] = {(a.type, a.name, a.ids): a for a in assets}
    keys = set(out['pc']) & set(out['x'])
    _cache[export_dir] = (out['pc'], out['x'], keys)
    return _cache[export_dir]
