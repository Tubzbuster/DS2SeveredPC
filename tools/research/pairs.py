"""PC/360 asset pairs from the export (tools/export), split per type by
`severed split` into <dir>/pc/<Type>.str and <dir>/x360/<Type>.str.

    for key, x360_payload, pc_payload in pairs.load(dir, 'Material'): ...
"""
import os
from ds2 import streamfile

DEFAULT = os.environ.get('DS2_PAIRS', '/tmp/claude-0/-home-user-DS2SeveredPC/55bfe32c-f5f8-5f82-90e0-34e8d63d0db0/scratchpad/exp')


def _assets(path):
    if not os.path.exists(path):
        return {}
    return {(a.type, a.name, a.ids): a for a in streamfile.read(open(path, 'rb').read())[1]}


def load(typ, root=DEFAULT, with_assets=False):
    pc = _assets(os.path.join(root, 'pc', typ + '.str'))
    x = _assets(os.path.join(root, 'x360', typ + '.str'))
    out = []
    for k in sorted(set(pc) & set(x)):
        if with_assets:
            out.append((k, x[k], pc[k]))
        else:
            out.append((k, x[k].payload(), pc[k].payload()))
    return out
