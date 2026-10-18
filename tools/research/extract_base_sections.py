"""Copies base-game hospital sections out of the PC archives (as stored),
to compare them with Severed's converted sections of the same name.

Severed reuses 47 of the base game's hospital section names
(ch01_hos\\ch01_hos\\<area>\\<section>\\<section>.str), so the base game's PC
files are a reference drawn by the same engine. The sections are EA's
data: keep the zip private (it is for the comparison only).

    py -3 extract_base_sections.py "<Dead Space 2 folder>" [section ...]
    py -3 extract_base_sections.py "<Dead Space 2 folder>" --all

Without section names it copies the airless hallway and the surgery ward
rooms. The zip is written next to this script: base_sections.zip.
"""
import glob
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds2 import bigarchive  # noqa: E402

AREAS = {
    'emergency': ['airless_hall_z01', 'emergency_arrival_z01'],
    'surgery_ward': ['surgery_pit_z01', 'surgery_z01', 'surgery_observation_z01', 'surgery_hall_z01',
                     'elev_surg_pit_z01', 'decontamination_z01', 'surgery_lobby_z01'],
}
DEFAULT = AREAS['emergency'] + AREAS['surgery_ward'][:3]


def severed_sections():
    """{section: area} for every Severed level section, from the add-on file list"""
    out = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for line in open(os.path.join(here, 'ds2', 'addon_hashes.txt')):
        if line.startswith('#') or not line.strip():
            continue
        p = line.split()[-1].replace('/', '\\')
        k = p.find('pdlc1_ch01_mng\\pdlc1_ch01_mng\\')
        rest = p[k + 30:].split('\\') if k >= 0 else []
        if len(rest) == 3 and rest[0] != 'shared' and p.endswith('.str'):
            out[rest[1]] = rest[0]
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        raise SystemExit(__doc__)
    game, wanted = args[0], args[1:]
    secs = severed_sections()
    idx = {}
    for p in sorted(glob.glob(os.path.join(game, 'DS2DAT*.DAT'))):
        if os.path.basename(p).upper() == 'DS2DAT2.DAT':
            continue                                  # Severed's own archive
        with open(p, 'rb') as f:
            i, _ = bigarchive.read_index(f)
        for h, (o, s) in i.items():
            idx.setdefault(h, (p, o, s))
    if '--all' in sys.argv:
        wanted = sorted(secs)
    elif not wanted:
        wanted = DEFAULT
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'base_sections.zip')
    found = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for s in wanted:
            area = secs.get(s)
            name = 'ch01_hos\\ch01_hos\\%s\\%s\\%s.str' % (area, s, s) if area else None
            h = bigarchive.name_hash(name) if name else None
            if h not in idx:
                print('  %-28s not in the base game' % s)
                continue
            p, o, n = idx[h]
            with open(p, 'rb') as f:
                f.seek(o)
                z.writestr('base/%s/%s.str' % (area, s), f.read(n))
            found += 1
            print('  %-28s %6.1f MB' % (s, n / 1e6))
    print('%d section(s) written to %s' % (found, out))


if __name__ == '__main__':
    main()
