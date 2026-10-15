"""Writes the class layouts the SimGroup converter needs, from probe v6's
dump of the PC engine's class descriptors:

    python3 export_schema.py severed_desc.bin deadspace2.exe ../ds2/simgroup_schema.json

Per class (key: sdbm hash of the lower-case name, hex): name, version,
struct size and fields [offset, type code, name] (+ [count, element type]
for type 0x13 inline arrays, + element class for arrays of structs; type
0x16 embedded structs carry their class).
"""
import sys, json
from dump import Dump

ARRAY = 0x13
STRUCT = 0x16


def main(desc_bin, exe, out):
    dm = Dump(desc_bin, exe)
    D = dm.descriptors()
    schema, missing = {}, []
    for va, (kind, name, w) in D.items():
        if kind != 'class':
            continue
        fl = dm.fields(w)
        if fl is None:
            missing.append(name)
            continue
        fields = []

        def class_hash(p):
            return '%08X' % D[p][2][2] if p in D and D[p][0] == 'class' else None
        for off, typ, fname, ti, extra in fl:
            f = [off, typ, fname]
            if typ == ARRAY:
                f += [dm.u32(ti), dm.u32(ti + 4)]   # count, element type
                if f[4] == STRUCT:
                    f.append(class_hash(dm.u32(ti + 8)))
            elif typ == STRUCT:
                f.append(class_hash(extra) or class_hash(dm.u32(ti + 8) if ti else None))
            fields.append(f)
        schema['%08X' % w[2]] = dict(name=name, version=w[3], size=w[16] >> 16, fields=fields)
    json.dump(schema, open(out, 'w'), indent=0, sort_keys=True)
    print('%d classes written, %d without a readable field list: %s' % (len(schema), len(missing), missing[:10]))


if __name__ == '__main__':
    main(*sys.argv[1:4])
