"""Index of the Severed assets the PC game already has (same type, name and
ids as a PC asset: the key that pairs the base game's PC and 360 assets):
ds2/pc_assets.json, {"type|name|id0..id4": "<archive entry hash>"} = the PC
stream holding it. Built from the asset listings of tools/index
(Index-Assets.ps1) of the PC install and of Severed:

    python3 learn_pc_assets.py <assets_pc.csv> <assets_severed.csv>

Holds names and hashes only; the assets themselves are read from the
user's own game archives (tools/test/make_severed_test.py)."""
import csv, json, os, sys
from ds2 import pcassets


def key(r):
    return pcassets.key(r['Type'], r['Name'], [int(r['Id%d' % i], 16) for i in range(5)])


def main(pc_csv, sev_csv):
    pc = {}
    for r in csv.DictReader(open(pc_csv, encoding='utf-8-sig')):
        if r['Type'] in pcassets.TYPES:
            pc.setdefault(key(r), r['Entry'])
    out = {}
    for r in csv.DictReader(open(sev_csv, encoding='utf-8-sig')):
        k = key(r)
        if r['Type'] in pcassets.TYPES and k in pc:
            out[k] = pc[k]
    path = os.path.join(os.path.dirname(__file__), 'ds2', 'pc_assets.json')
    json.dump(out, open(path, 'w'), indent=0, sort_keys=True)
    print(len(out), 'assets ->', path)


if __name__ == '__main__':
    main(*sys.argv[1:3])
