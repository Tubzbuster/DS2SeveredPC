"""360 self-describing SimGroups (91C8773C) -> the PC's same format.

Unlike packed records, these store property types, enum strings and shared
value pools. Keep that representation: the PC engine already reads it.
Offsets are relative to each property's value word, including backwards
references to embedded nodes. No game data or class defaults are embedded.
"""
import struct
from . import simgroup as S


# The same objects have different content hashes in the two serializations.
# Map only the objects used by the existing, targeted gameplay fixes.
OBJECT_HASHES = {
    0x9A01ECF8: 0x85239AE0,     # mining camp TriggerAuto
    0x8482720A: 0xD13CFBBE,     # quarry TriggerAuto
    0x3A73B1ED: 0x4B5F383F,     # Quarry checkpoint restore
    0x1DAB53F7: 0xE5EF38AC,     # ses_player_igc_01_05
    0xCC9E3396: 0xA997200F,     # its PlayAudioStream
    0x4F5F4826: 0x5EAA9249,     # mm_ses_01_03_trigger
    0x7E602E20: 0xC767274B,     # ses_player_01_03
    0x1C5B314A: 0x2E30A6F6,     # drill tunnel corpse
    0x34464104: 0xAF37A013,     # drill tunnel corpse
    0x4C8A721A: 0x3CB7C77C,     # Oracle corpse
    0xD6FBEF2C: 0x49D4A20B,     # Oracle corpse (Key object bodies on limp)
}

POINTER_TYPES = {12: 16, 13: 12, 14: 16, 15: 64}
SCALAR_TYPES = {0, 1, 2, 3, 4, 5, 7, 8, 10, 11, 16, 17, 22}


def convert(x, stats):
    b = (struct.unpack_from('>I', x, 4)[0] + 15) & ~15

    def bounds(o, size):
        if o < 0 or size < 0 or o + size > len(x):
            raise S.Unknown('property-tree range outside SimGroup')

    bounds(b, 0x20)
    magic, size, hs, nt, reserved, no, nn, po, pn = struct.unpack_from('>IIIHHIIII', x, b)
    if magic != S.OLD_BLOCK or b + size != len(x) or hs != 0x20:
        raise S.Unknown('invalid property-tree header')
    bounds(b + hs, 8 * nt)
    bounds(b + no, 12 * nn)
    bounds(b + po, 12 * pn)
    out = bytearray(x)
    S._swap(out, x, 0, b, 4)
    for o in (0x14, 0x18):
        S._swap(out, x, o, 4, 2)
    S._swap(out, x, b, 12, 4)
    S._swap(out, x, b + 12, 4, 2)
    S._swap(out, x, b + 16, 16, 4)
    S._swap(out, x, b + hs, 8 * nt, 4)
    types = [struct.unpack_from('>II', x, b + hs + 8 * i)[0] for i in range(nt)]
    sch = S.schema()
    by_name = {c['name']: (h, c) for h, c in sch.items()}
    mapped = list(types)
    neutral = set()
    for i, h in enumerate(types):
        if h in S.NEUTRAL and h not in sch:
            mapped[i] = by_name[S.NEUTRAL_AS][0]
            neutral.add(i)
            stats['neutralised'] = stats.get('neutralised', 0) + 1
        elif h in S.REMAP and h not in sch:
            mapped[i] = by_name[S.REMAP[h]][0]
            counts = stats.setdefault('remapped', {})
            counts[S.REMAP[h]] = counts.get(S.REMAP[h], 0) + 1
        struct.pack_into('<I', out, b + hs + 8 * i, mapped[i])

    # Property rows: [name hash, enum type index, type, array index, value,
    # absolute pointer target or None]. Keep source addresses for shared data.
    props = []
    swapped = set()

    def pool(o, length):
        bounds(o, length)
        for at in range(o, o + length, 4):
            if at not in swapped:
                out[at:at + 4] = x[at:at + 4][::-1]
                swapped.add(at)

    def string(o):
        if o is None:
            return b''
        bounds(o, 1)
        end = x.find(b'\0', o)
        if end < 0:
            raise S.Unknown('unterminated property-tree string')
        return x[o:end]

    for i in range(pn):
        o = b + po + 12 * i
        h, enum, typ, index, value = struct.unpack_from('>IHBBI', x, o)
        if enum != 0xFFFF and enum >= nt:
            raise S.Unknown('invalid property enum index')
        pointer = typ in POINTER_TYPES or typ in (16, 17, 22) or enum != 0xFFFF
        # Zero is a null/default value, not a pointer back into the row.
        target = o + 8 + struct.unpack_from('>i', x, o + 8)[0] if pointer and value else None
        if typ in POINTER_TYPES and target is not None:
            pool(target, POINTER_TYPES[typ])
        elif typ not in SCALAR_TYPES and typ not in POINTER_TYPES:
            raise S.Unknown('property-tree type %#x' % typ)
        if target is not None and (typ in (16, 17) or enum != 0xFFFF):
            string(target)
        if typ == 22 and target is not None:
            if target < b + no or (target - b - no) % 12 or target >= b + no + 12 * nn:
                raise S.Unknown('invalid embedded property-tree node')
        struct.pack_into('<IHBB', out, o, h, enum, typ, index)
        if pointer or typ not in (3, 4, 5, 7, 8):
            struct.pack_into('<I', out, o + 8, value)
        elif typ in (3, 4):
            out[o + 8:o + 10] = x[o + 8:o + 10][::-1]
        value = struct.unpack_from('<I', out, o + 8)[0]
        props.append([h, enum, typ, index, value, target])

    nodes = []
    by_obj = {}
    for i in range(nn):
        o = b + no + 12 * i
        oh, ti, count, children = struct.unpack_from('>IHHI', x, o)
        if ti >= nt:
            raise S.Unknown('invalid property-tree class index')
        bounds(b + children, 2 * count)
        ids = list(struct.unpack_from('>%dH' % count, x, b + children))
        if any(p >= pn for p in ids):
            raise S.Unknown('invalid property-tree property index')
        struct.pack_into('<IHHI', out, o, oh, ti, count, children)
        # Lists may overlap, so always swap from x, never from out.
        S._swap(out, x, b + children, 2 * count, 2)
        if ti in neutral:
            struct.pack_into('<H', out, o + 6, 0)
            ids = []
        nodes.append((o, oh, ti, ids))
        by_obj[oh] = (types[ti], mapped[ti])

    # Group hashes depend on the native byte order of member class hashes.
    oC, o10 = struct.unpack_from('>II', x, 12)
    n14, n16, n18 = struct.unpack_from('>HHH', x, 0x14)
    if o10:
        bounds(o10, 4 * n18)
        for i in range(n18):
            e = struct.unpack_from('>I', x, o10 + 4 * i)[0]
            bounds(e, 8)
            count = struct.unpack_from('>I', x, e + 4)[0]
            bounds(e + 8, 4 * count)
            offsets = struct.unpack_from('>%dI' % count, x, e + 8)
            members = []
            for q in offsets:
                bounds(q, 4)
                oh = struct.unpack_from('>I', x, q)[0]
                if oh not in by_obj:
                    raise S.Unknown('property-tree group member not found')
                members.append(by_obj[oh])
            before = S.sdbm(struct.pack('>%dI' % count, *[m[0] for m in members]))
            if before != struct.unpack_from('>I', x, e)[0]:
                stats['group_hash_unverified'] = stats.get('group_hash_unverified', 0) + 1
            else:
                struct.pack_into('<I', out, e, S.sdbm(struct.pack('<%dI' % count, *[m[1] for m in members])))
    bounds(oC, 0x44 * n16)
    S._nudge(out, x, oC, n16, stats)

    # Apply the packed converter's fixes by schema field name/offset. Edited
    # properties are cloned: both property rows and their values may be shared
    # by other nodes, which must not be changed as a side effect.
    present = {OBJECT_HASHES.get(oh, oh) for _, oh, _, _ in nodes}
    ragdoll = {h: f for rs in S.RAGDOLL_SETS if all(h in present for h in rs) for h, f in rs.items()}
    edits = {}

    def append(data):
        at = len(out)
        out.extend(data)
        return at

    for node, oh, ti, ids in nodes:
        cls = sch.get(mapped[ti])
        if cls is None or ti in neutral:
            continue
        key = OBJECT_HASHES.get(oh, oh)
        fields = {S.msg_hash(f[2].encode()): f for f in cls['fields']}
        slots = {fields[props[p][0]][0]: p for p in ids if props[p][0] in fields}
        changed = list(ids)

        def set_prop(off, value=None, text=None):
            field = next((f for f in cls['fields'] if f[0] == off), None)
            if field is None:
                raise S.Unknown('gameplay fix field not found')
            old = slots.get(off)
            if old is None:
                row = [S.msg_hash(field[2].encode()), 0xFFFF, field[1], 0xFF, 0, None]
            else:
                row = list(props[old])
            if text is not None:
                row[5] = append(text + b'\0')
            else:
                row[1], row[4], row[5] = 0xFFFF, value, None
            props.append(row)
            pi = len(props) - 1
            if old is None:
                changed.append(pi)
            else:
                changed[changed.index(old)] = pi
            slots[off] = pi

        def retarget(off, old, new):
            pi = slots.get(off)
            if pi is not None and props[pi][2] == 17 and string(props[pi][5]) == old:
                set_prop(off, text=new)
                stats['retargeted'] = stats.get('retargeted', 0) + 1
            else:
                stats['retarget_skipped'] = stats.get('retarget_skipped', 0) + 1

        for off, old, new in S.FIELD_RETARGET.get(key, []):
            retarget(off, old, new)
        if key in S.RETARGET:
            retarget(0, *S.RETARGET[key])
        if key in S.AUTO_OPTIONS and cls['name'] == 'TriggerAuto':
            set_prop(16, value=S.AUTO_OPTIONS[key][1])
            stats['auto_options'] = stats.get('auto_options', 0) + 1
        if key in ragdoll and cls['name'] == 'RagdollComponent':
            set_prop(16, value=ragdoll[key])
            stats['ragdoll_flags'] = stats.get('ragdoll_flags', 0) + 1
        if key in S.SES_FLAGS and cls['name'] == 'ScriptedEventSequence':
            set_prop(116, value=S.SES_FLAGS[key][1])
            stats['ses_flags'] = stats.get('ses_flags', 0) + 1
        for off, (target, was, now) in S.DELAYS.get(key, {}).items():
            pi, msg = slots.get(off), slots.get(off - 12)
            if pi is not None and msg is not None and props[pi][2] == 0 and props[msg][2] == 17 \
                    and S.msg_hash(string(props[msg][5])) == target \
                    and abs(struct.unpack('>f', struct.pack('>I', props[pi][4]))[0] - was) < 1e-3:
                set_prop(off, value=struct.unpack('>I', struct.pack('>f', now))[0])
                stats['delays'] = stats.get('delays', 0) + 1
            else:
                stats['delay_skipped'] = stats.get('delay_skipped', 0) + 1
        if cls['name'] == 'AnimateLight':
            off = {f[2]: f[0] for f in cls['fields']}
            keys = ('CMD_IntensityJitter', 'CMD_IntensityJitterMin', 'CMD_Frequency')
            # Omitted values use engine defaults; only alter explicitly stored
            # values whose range can be checked, rather than inventing defaults.
            if all(off[k] in slots for k in keys):
                jit, jmin, freq = [struct.unpack('>f', struct.pack('>I', props[slots[off[k]]][4]))[0] for k in keys]
                if 0 < freq < S.CALM_PERIOD and jit - jmin > 1:
                    for k, v in zip(keys, (S.CALM_RANGE[1], S.CALM_RANGE[0], S.CALM_SLOW)):
                        set_prop(off[k], value=struct.unpack('>I', struct.pack('>f', v))[0])
                    stats['lights_calmed'] = stats.get('lights_calmed', 0) + 1
        if cls['name'] == 'ItemStoreList':
            entries = [p for p in ids if props[p][2] == 12]
            kept = [p for p in entries if props[p][5] is None
                    or struct.unpack_from('>II', x, props[p][5]) not in S.STORE_HIDDEN]
            if len(kept) != len(entries):
                values = [bytes(out[props[p][5]:props[p][5] + 16]) if props[p][5] is not None else bytes(16)
                          for p in kept]
                values += [bytes(16)] * (len(entries) - len(kept))
                for old, value in zip(entries, values):
                    row = list(props[old])
                    row[5] = append(value)
                    props.append(row)
                    changed[changed.index(old)] = len(props) - 1
                stats['store_items_hidden'] = stats.get('store_items_hidden', 0) + len(entries) - len(kept)
        if changed != ids:
            edits[node] = changed

    if edits:
        out.extend(bytes(-len(out) % 4))
        at = len(out)
        for h, enum, typ, index, value, target in props:
            if target is not None:
                value = (target - (len(out) + 8)) & S.M
            out.extend(struct.pack('<IHBBI', h, enum, typ, index, value))
        struct.pack_into('<II', out, b + 0x18, at - b, len(props))
        for node, ids in edits.items():
            if len(props) > 0x10000 or len(ids) > 0xFFFF:
                raise S.Unknown('too many property-tree properties')
            at = append(struct.pack('<%dH' % len(ids), *ids))
            struct.pack_into('<HI', out, node + 6, len(ids), at - b)
        struct.pack_into('<I', out, b + 4, len(out) - b)
    stats['property_tree'] = stats.get('property_tree', 0) + 1
    return bytes(out)
