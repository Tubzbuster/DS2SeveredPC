"""Score a converter against all exported pairs of a type.

    python3 score.py tg4h [--show N]
"""
import sys, collections
import pairs
from ds2 import convert


def main(typ, show=0):
    P = pairs.load(typ)
    fn = convert.CONVERTERS[typ]
    res = collections.Counter()
    bad = []
    for k, x, p in P:
        try:
            y = fn(x)
        except Exception as e:
            y = e
        if isinstance(y, Exception):
            res['error'] += 1; bad.append((k, x, p, y))
        elif y is None:
            res['not handled'] += 1; bad.append((k, x, p, None))
        elif y == p:
            res['exact'] += 1
        else:
            res['wrong'] += 1; bad.append((k, x, p, y))
    n = len(P)
    print('%s: %d pairs: %s  -> %.2f%% exact' % (typ, n, dict(res), 100.0 * res['exact'] / max(n, 1)))
    for k, x, p, y in bad[:show]:
        print('--', k[1], len(x), len(p), type(y).__name__ if not isinstance(y, (bytes, type(None))) else '')
        print('  360', x[:0x60].hex(' '))
        print('  PC ', p[:0x60].hex(' '))
        if isinstance(y, bytes):
            print('  got', y[:0x60].hex(' '))
    return res


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == '--show' else 0)
