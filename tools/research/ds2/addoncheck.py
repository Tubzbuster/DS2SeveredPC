"""Checks an unpacked Severed add-on against supported versions.
addon_hashes.txt holds the reference version's MD5, size and path for all
421 files. Other known versions are identified by a fingerprint of their
complete file list, not by allowing arbitrary mismatches. The check works
on the files inside, not the package, so header/licence changes and fully
extracted folders are supported alike.

    problems = addoncheck.check(root)      # [] when the copy is as expected
"""
import hashlib
import os

LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'addon_hashes.txt')

# SHA256 of sorted "md5 size path\n" rows for all required files (UTF-8).
# Metadata only, no game data. This version has the same paths and sizes
# as the reference, with 164 different file hashes. Do not accept a mixture
# of versions: the complete set must match one fingerprint.
KNOWN_VARIANTS = {
    'f108f8bf43fdde32c1b61b1daa75a2d9bde1551f5543775752ff0b2674c9bd15':
        'Xbox 360 package 1B7ECDF80282FF1C61F83A1423FD91B4A3C8827E45',
}


def expected():
    """{path: (md5, size)}"""
    out = {}
    with open(LIST, encoding='utf-8') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                md5, size, path = line.split(None, 2)
                out[path.strip()] = (md5, int(size))
    return out


def fingerprint(entries):
    """SHA256 of {normalized path: (md5, size)}, independent of row order."""
    h = hashlib.sha256()
    for path, (md5, size) in sorted(entries.items()):
        h.update(('%s %d %s\n' % (md5, size, path)).encode('utf-8'))
    return h.hexdigest()


def _md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check(root, progress=None):
    """Problems at root, or [] for a complete supported version.

    Unknown versions still report differences against addon_hashes.txt.
    Extra files are ignored, as before; missing or resized required files
    cannot match a known variant.
    """
    want = expected()
    have = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            have[os.path.relpath(p, root).replace('\\', '/').lower()] = p
    problems = []
    actual = {}
    for i, (path, (md5, size)) in enumerate(sorted(want.items())):
        if progress and i % 50 == 0:
            progress(i, len(want))
        p = have.get(path.lower())
        if p is None:
            problems.append('missing: ' + path)
        elif os.path.getsize(p) != size:
            problems.append('wrong size: %s (%d bytes, expected %d)' % (path, os.path.getsize(p), size))
        else:
            digest = _md5(p)
            actual[path.lower()] = (digest, size)
            if digest != md5:
                problems.append('different contents: ' + path)
    if problems and len(actual) == len(want) and fingerprint(actual) in KNOWN_VARIANTS:
        return []
    return problems
