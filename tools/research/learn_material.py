"""Learn the Material 360 -> PC shader-setup table from the exported pairs.

For every 360 pass setup (3 passes) seen in a PC/360 pair of the same
material, record the PC passes and which parameters (by hash) the PC
version appends. Writes ds2/material_table.json.
"""
import json, collections, struct, sys
import pairs
from ds2 import streamfile, material as M


def setup_key(passes):
    return ','.join('%08X:%08X:%08X:%s' % (s, f, t, tl.hex()) for s, f, t, tl in passes)


def main():
    R = pairs.DEFAULT
    pc = collections.defaultdict(list)
    for a in streamfile.read(open(R + '/pc/Material.str', 'rb').read())[1]:
        pc[a.name.lower()].append(a)
    table = collections.defaultdict(collections.Counter)
    for a in streamfile.read(open(R + '/x360/Material.str', 'rb').read())[1]:
        cands = pc.get(a.name.lower())
        if not cands:
            continue
        b = next((c for c in cands if c.ids[0] == a.ids[0]), cands[0])
        x, p = M.parse(a.payload(), True), M.parse(b.payload(), False)
        n = len(x.params)
        if p.params[:n] != x.params:
            continue  # not the same material content
        extra = tuple(e[0] for e in p.params[n:])
        table[setup_key(x.passes)][(setup_key(p.passes), extra)] += 1
    out, conflicts = {}, 0
    for k, v in table.items():
        (pcs, extra), cnt = v.most_common(1)[0]
        if len(v) > 1:
            conflicts += 1
        out[k] = {'pc': pcs, 'append': ['%08X' % h for h in extra], 'seen': sum(v.values())}
    json.dump(out, open('ds2/material_table.json', 'w'), indent=0, sort_keys=True)
    print('%d 360 setups learned, %d with conflicting PC versions' % (len(out), conflicts))


if __name__ == '__main__':
    main()
