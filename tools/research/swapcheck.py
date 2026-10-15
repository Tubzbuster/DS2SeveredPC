"""For PC/360 asset pairs of equal size, measure how much matches after
byte-swapping 32-bit words, 16-bit words, or nothing."""
import sys, collections, struct
from ds2 import streamfile


def load(path):
    return {(a.type, a.name): a for a in streamfile.read(open(path, 'rb').read())[1]}


def score(a, b):
    n = len(a) // 4 * 4
    if n == 0:
        return (0, 0, 0)
    wa = struct.unpack('<%dI' % (n // 4), a[:n])
    wb_be = struct.unpack('>%dI' % (n // 4), b[:n])            # 32-bit swap
    wb_same = struct.unpack('<%dI' % (n // 4), b[:n])          # no swap
    ha = struct.unpack('<%dH' % (n // 2), a[:n])
    hb = struct.unpack('>%dH' % (n // 2), b[:n])                # 16-bit swap
    s32 = sum(x == y for x, y in zip(wa, wb_be)) / len(wa)
    s0 = sum(x == y for x, y in zip(wa, wb_same)) / len(wa)
    s16 = sum(x == y for x, y in zip(ha, hb)) / len(ha)
    return s32, s16, s0


def main(pairs):
    agg = collections.defaultdict(list)
    for p, x in pairs:
        pc, xx = load(p), load(x)
        for k in set(pc) & set(xx):
            a, b = pc[k].payload(), xx[k].payload()
            if len(a) == len(b) and a != b:
                agg[k[0]].append(score(a, b) + (len(a),))
    print('%-18s %5s %9s %9s %9s %9s' % ('type', 'n', 'swap32', 'swap16', 'noswap', 'best32>99%'))
    for t, v in sorted(agg.items(), key=lambda kv: -len(kv[1])):
        n = len(v)
        print('%-18s %5d %8.1f%% %8.1f%% %8.1f%% %9d' % (t, n, 100 * sum(x[0] for x in v) / n, 100 * sum(x[1] for x in v) / n,
                                                     100 * sum(x[2] for x in v) / n, sum(1 for x in v if x[0] > 0.99)))


if __name__ == '__main__':
    a = sys.argv[1:]
    main(list(zip(a[0::2], a[1::2])))
