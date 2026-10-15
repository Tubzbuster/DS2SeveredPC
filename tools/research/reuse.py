"""Match Severed assets against the PC game's assets using the index CSVs
written by tools/index/Index-Assets.ps1.

    python3 reuse.py assets_pc.csv assets_severed.csv

An asset is identified by (type, name, Id0..Id4); the IDs are the same on
PC and 360 for the same content (verified on base-game pairs for every type
except APX). Reports, per type, how many distinct Severed assets the PC game
already has identically, has in another version, or lacks entirely.
"""
import csv, collections, sys


def key(r):
    return (r['Type'], r['Name'].lower(), r['Id0'], r['Id1'], r['Id2'], r['Id3'], r['Id4'])


def main(pc_csv, sev_csv):
    pc, pc_names = set(), set()
    for r in csv.DictReader(open(pc_csv, encoding='utf-8-sig')):
        pc.add(key(r))
        pc_names.add((r['Type'], r['Name'].lower()))
    sev = {}
    rows = 0
    for r in csv.DictReader(open(sev_csv, encoding='utf-8-sig')):
        rows += 1
        sev.setdefault(key(r), r)
    cats = ['in PC (identical)', 'in PC (other version)', 'new in Severed']
    count, size = collections.Counter(), collections.Counter()
    by_type = collections.defaultdict(collections.Counter)
    for k, r in sev.items():
        c = cats[0] if k in pc else cats[1] if k[:2] in pc_names else cats[2]
        count[c] += 1
        size[c] += int(r['Size'])
        by_type[k[0]][c] += 1
    total = sum(size.values())
    print('Severed: %d asset rows, %d distinct assets, %.1f MB' % (rows, len(sev), total / 1e6))
    for c in cats:
        print('  %-24s %6d assets %8.1f MB (%4.1f%%)' % (c, count[c], size[c] / 1e6, 100 * size[c] / total))
    print('\n%-20s' % 'type' + ''.join('%24s' % c for c in cats))
    for t in sorted(by_type, key=lambda t: -sum(by_type[t].values())):
        print('%-20s' % t + ''.join('%24d' % by_type[t][c] for c in cats))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
