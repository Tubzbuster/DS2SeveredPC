"""Checks an unpacked Severed add-on against the expected file list
(addon_hashes.txt: MD5, size and path of each of its 421 files), so a
damaged or different copy is reported before converting. The check works
on the files inside, not the package, so copies whose header or licences
differ (European, World) pass alike.

    problems = addoncheck.check(root)      # [] when the copy is as expected
"""
import hashlib
import os

LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'addon_hashes.txt')


def expected():
    """{path: (md5, size)}"""
    out = {}
    for line in open(LIST, encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            md5, size, path = line.split(None, 2)
            out[path.strip()] = (md5, int(size))
    return out


def _md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check(root, progress=None):
    """problems found in the unpacked add-on at root, one line each"""
    want = expected()
    have = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            have[os.path.relpath(p, root).replace('\\', '/').lower()] = p
    problems = []
    for i, (path, (md5, size)) in enumerate(sorted(want.items())):
        if progress and i % 50 == 0:
            progress(i, len(want))
        p = have.get(path.lower())
        if p is None:
            problems.append('missing: ' + path)
        elif os.path.getsize(p) != size:
            problems.append('wrong size: %s (%d bytes, expected %d)' % (path, os.path.getsize(p), size))
        elif _md5(p) != md5:
            problems.append('different contents: ' + path)
    return problems
