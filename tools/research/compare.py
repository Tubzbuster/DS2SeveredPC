"""Compare the assets of a PC and an Xbox 360 stream file asset by asset.

    python3 -m compare PC.str 360.str [more pairs...]

For every asset present in both (matched by name and type), decompress both
and report whether the payloads are identical, the same size, or different.
"""
import sys, collections, time
from ds2 import streamfile


def load(path):
    be, assets = streamfile.read(open(path, 'rb').read())
    return {(a.type, a.name): a for a in assets}


def main(pairs):
    stats = collections.defaultdict(collections.Counter)
    errors = collections.Counter()
    for pc_path, x_path in pairs:
        pc, x = load(pc_path), load(x_path)
        t = time.time()
        for key in sorted(set(pc) & set(x)):
            typ = key[0]
            try:
                a, b = pc[key].payload(), x[key].payload()
            except Exception as e:  # report and carry on
                errors[(typ, type(e).__name__ + ': ' + str(e)[:60])] += 1
                continue
            if a == b:
                stats[typ]['identical'] += 1
            elif len(a) == len(b):
                stats[typ]['same size'] += 1
            else:
                stats[typ]['different size'] += 1
        for key in set(x) - set(pc):
            stats[key[0]]['360 only'] += 1
        for key in set(pc) - set(x):
            stats[key[0]]['PC only'] += 1
        print('%s: %.1fs' % (pc_path, time.time() - t), file=sys.stderr)
    cols = ['identical', 'same size', 'different size', '360 only', 'PC only']
    print('%-20s' % 'type' + ''.join('%15s' % c for c in cols))
    for typ in sorted(stats, key=lambda t: -sum(stats[t].values())):
        print('%-20s' % typ + ''.join('%15d' % stats[typ][c] for c in cols))
    for (typ, msg), n in errors.most_common():
        print('ERROR %-12s x%-4d %s' % (typ, n, msg))


if __name__ == '__main__':
    args = sys.argv[1:]
    main(list(zip(args[0::2], args[1::2])))
