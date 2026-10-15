"""Runs a converter over every Severed asset of a type (no PC version to
compare with: counts converted / not handled / errors).

    python3 coverage.py MetaModel [severed_dir]
"""
import os, sys, collections
from ds2 import streamfile, convert

SEVERED = os.environ.get('DS2_SEVERED', '/tmp/claude-0/-home-user-DS2SeveredPC/55bfe32c-f5f8-5f82-90e0-34e8d63d0db0/scratchpad/sev/x')


def severed_assets(typ, root=SEVERED):
    seen = set()
    for d, _, files in os.walk(root):
        for f in sorted(files):
            if f.endswith('.str'):
                for a in streamfile.read(open(os.path.join(d, f), 'rb').read())[1]:
                    k = (a.type, a.name, a.ids)
                    if a.type == typ and k not in seen:
                        seen.add(k)
                        yield a


def main(typ, root=SEVERED):
    fn = convert.CONVERTERS[typ]
    c = collections.Counter()
    for a in severed_assets(typ, root):
        try:
            y = fn(a.payload())
            c['converted' if y is not None else 'not handled'] += 1
        except Exception as e:
            c['error: %s' % type(e).__name__] += 1
    print(typ, dict(c))


if __name__ == '__main__':
    main(sys.argv[1], *sys.argv[2:3])
