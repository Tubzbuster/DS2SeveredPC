"""PC/360 asset pairs from the export (tools/export), split per type by
`severed split` into <dir>/pc/<Type>.str and <dir>/x360/<Type>.str.

    for key, x360_payload, pc_payload in pairs.load(dir, 'Material'): ...
"""
import os
from ds2 import streamfile

DEFAULT = os.environ.get('DS2_PAIRS', '/tmp/claude-0/-home-user-DS2SeveredPC/55bfe32c-f5f8-5f82-90e0-34e8d63d0db0/scratchpad/exp')


def _assets(path, by_name=False):
    if not os.path.exists(path):
        return {}
    out = {}
    for a in streamfile.read(open(path, 'rb').read())[1]:
        if by_name:
            # NAV: names end in .win (PC) / .xen (360), IDs differ
            n = a.name.lower().rsplit('.', 1)[0]
            out[(a.type, n, None)] = None if (a.type, n, None) in out else a
        else:
            out[(a.type, a.name, a.ids)] = a
    return {k: v for k, v in out.items() if v is not None}


BY_NAME = {'NAV'}


def load(typ, root=DEFAULT, with_assets=False):
    bn = typ in BY_NAME
    pc = _assets(os.path.join(root, 'pc', typ + '.str'), bn)
    x = _assets(os.path.join(root, 'x360', typ + '.str'), bn)
    out = []
    for k in sorted(set(pc) & set(x)):
        if with_assets:
            out.append((k, x[k], pc[k]))
        else:
            out.append((k, x[k].payload(), pc[k].payload()))
    return out
