"""Prints an Xbox 360 add-on package's header fields and the MD5 of every file
inside, to compare copies of Severed from different regions. No game data is
written: only names, sizes, IDs and hashes.

    py -3 addon_info.py <package file or unpacked folder> [...]

Each input gets <name>.addoninfo.txt next to this script.
"""
import hashlib, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'research'))
from ds2 import stfs  # noqa: E402

LOCALES = ('English', 'Japanese', 'German', 'French', 'Spanish', 'Italian', 'Korean', 'Chinese (Trad.)',
           'Portuguese', 'Chinese (Simpl.)', 'Polish', 'Russian')


def _utf16(d, o, n=0x80):
    return d[o:o + n].decode('utf-16-be', 'replace').split('\0')[0]


def header_lines(d):
    u32 = lambda o: struct.unpack_from('>I', d, o)[0]
    out = ['magic             %s' % d[:4].decode('latin1'),
           'content ID (SHA1) %s' % d[0x32C:0x340].hex().upper(),
           'content type      %08X' % u32(0x344),
           'metadata version  %d' % u32(0x348),
           'content size      %d' % struct.unpack_from('>Q', d, 0x34C)[0],
           'media ID          %08X' % u32(0x354),
           'version           %d' % u32(0x358),
           'base version      %d' % u32(0x35C),
           'title ID          %08X' % u32(0x360),
           'platform          %d' % d[0x364],
           'console ID        %s' % d[0x36C:0x371].hex().upper(),
           'profile ID        %s' % d[0x371:0x379].hex().upper(),
           'device ID         %s' % d[0x3FD:0x411].hex().upper(),
           'publisher         %s' % _utf16(d, 0x1611),
           'title name        %s' % _utf16(d, 0x1691)]
    for i in range(16):
        lid, bits, flags = struct.unpack_from('>QII', d, 0x22C + 16 * i)
        if lid or bits or flags:
            out.append('licence %-2d        id %016X bits %08X flags %08X' % (i, lid, bits, flags))
    for i, name in enumerate(LOCALES):
        t = _utf16(d, 0x411 + 0x80 * i)
        if t:
            out.append('name %-17s %s' % (name, t))
    return out


def package_files(path):
    d = open(path, 'rb').read()
    return header_lines(d), ((p, data) for p, data in stfs.files(d))


def folder_files(root):
    def walk():
        for dp, _, fs in os.walk(root):
            for f in fs:
                full = os.path.join(dp, f)
                yield os.path.relpath(full, root).replace('\\', '/'), open(full, 'rb').read()
    return ['unpacked folder (no package header)'], walk()


def main(paths):
    if not paths:
        print(__doc__)
        return 1
    for p in paths:
        head, files = (folder_files if os.path.isdir(p) else package_files)(p)
        rows = sorted('%s  %10d  %s' % (hashlib.md5(data).hexdigest(), len(data), name) for name, data in files)
        name = os.path.basename(os.path.normpath(p))
        out = os.path.join(HERE, name + '.addoninfo.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(['input             ' + name] + head + ['', '%d files' % len(rows)] + rows) + '\n')
        print('%s: %d files -> %s' % (name, len(rows), out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
