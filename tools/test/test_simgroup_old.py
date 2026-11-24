"""Synthetic property-tree conversion tests; no game files required."""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research'))
from ds2 import simgroup as S  # noqa: E402


def prop(name, typ, value, enum=0xFFFF, index=0xFF):
    return (S.msg_hash(name.encode()), enum, typ, index, value)


def group(types, nodes, properties, with_group=False):
    """Build a small BE property tree. bytes values go into the value pool;
    ('node', index) is a backwards reference to an embedded node."""
    head = bytearray(0x40)
    if with_group:
        # One group containing the first node, via a header hash pointer.
        head.extend(struct.pack('>I', nodes[0][0]))
        g = len(head)
        head.extend(struct.pack('>III', S.sdbm(struct.pack('>I', types[nodes[0][1]])), 1, 0x40))
        table = len(head)
        head.extend(struct.pack('>I', g))
        struct.pack_into('>I', head, 0x10, table)
        struct.pack_into('>H', head, 0x18, 1)
    head.extend(bytes(-len(head) % 16))
    b = len(head)
    struct.pack_into('>I', head, 4, b)
    no = 0x20 + 8 * len(types)
    po = no + 12 * len(nodes)
    data = bytearray(po + 12 * len(properties))
    struct.pack_into('>IIIHHIIII', data, 0, S.OLD_BLOCK, 0, 0x20, len(types), 0,
                     no, len(nodes), po, len(properties))
    for i, h in enumerate(types):
        struct.pack_into('>II', data, 0x20 + 8 * i, h, 1)
    for i, (oh, ti, ids) in enumerate(nodes):
        at = len(data)
        data.extend(struct.pack('>%dH' % len(ids), *ids))
        struct.pack_into('>IHHI', data, no + 12 * i, oh, ti, len(ids), at)
    for i, (h, enum, typ, index, value) in enumerate(properties):
        o = po + 12 * i
        if isinstance(value, bytes):
            at = len(data)
            data.extend(value)
            value = at - (o + 8)
        elif isinstance(value, tuple):
            value = no + 12 * value[1] - (o + 8)
        struct.pack_into('>IHBBI', data, o, h, enum, typ, index, value & 0xFFFFFFFF)
    struct.pack_into('>I', data, 4, len(data))
    return bytes(head + data)


def read_nodes(y):
    b = (struct.unpack_from('<I', y, 4)[0] + 15) & ~15
    _, size, _, _, _, no, nn, po, pn = struct.unpack_from('<IIIHHIIII', y, b)
    assert b + size == len(y)
    result = {}
    for i in range(nn):
        oh, ti, count, children = struct.unpack_from('<IHHI', y, b + no + 12 * i)
        rows = {}
        for pi in struct.unpack_from('<%dH' % count, y, b + children):
            assert pi < pn
            o = b + po + 12 * pi
            h, enum, typ, index, value = struct.unpack_from('<IHBBI', y, o)
            target = o + 8 + struct.unpack_from('<i', y, o + 8)[0]
            if value == 0 and (typ in (12, 13, 14, 15, 16, 17, 22) or enum != 0xFFFF):
                value = None
            elif typ in (16, 17) or enum != 0xFFFF:
                value = y[target:y.index(b'\0', target)]
            elif typ in (12, 13, 14, 15):
                n = {12: 16, 13: 12, 14: 16, 15: 64}[typ]
                value = struct.unpack_from('<%dI' % (n // 4), y, target)
            elif typ == 22:
                value = struct.unpack_from('<I', y, target)[0]
            rows[h] = (typ, index, value)
        result[oh] = rows
    return result


class PropertyTreeTests(unittest.TestCase):
    def schema(self, name='Test', fields=()):
        return {123: {'name': name, 'fields': list(fields), 'size': 64, 'version': 1},
                456: {'name': 'NavFolder', 'fields': [], 'size': 0, 'version': 1}}

    def convert(self, x, schema=None):
        stats = {}
        with mock.patch.object(S, 'schema', return_value=schema or self.schema()):
            y = S.convert(x, stats)
        self.assertIsNotNone(y)
        return y, stats

    def test_typed_values_and_backwards_struct_reference(self):
        ps = [prop('float', 0, 0x3F800000), prop('integer', 2, 0x12345678),
              prop('bool', 7, 0x01000000), prop('short', 3, 0x12340000),
              prop('string', 17, b'unchanged text\0'),
              prop('guid', 12, struct.pack('>4I', 1, 2, 3, 4)),
              prop('vector', 13, struct.pack('>3I', 5, 6, 7)),
              prop('matrix', 15, struct.pack('>16I', *range(16))),
              prop('struct', 22, ('node', 1)), prop('enum', 1, b'FLAG_A|FLAG_B\0', enum=0)]
        x = group([123], [(10, 0, list(range(len(ps)))), (11, 0, [])], ps)
        y, stats = self.convert(x)
        rows = read_nodes(y)[10]
        for name, expected in [('float', 0x3F800000), ('integer', 0x12345678), ('bool', 1),
                               ('short', 0x1234), ('string', b'unchanged text'),
                               ('guid', (1, 2, 3, 4)), ('vector', (5, 6, 7)),
                               ('matrix', tuple(range(16))), ('struct', 11), ('enum', b'FLAG_A|FLAG_B')]:
            self.assertEqual(rows[S.msg_hash(name.encode())][2], expected)
        self.assertEqual(stats['property_tree'], 1)

    def test_shared_value_pool_swapped_once(self):
        ps = [prop('a', 12, struct.pack('>4I', 1, 2, 3, 4)), prop('b', 12, bytes(16))]
        x = bytearray(group([123], [(10, 0, [0, 1])], ps))
        b = struct.unpack_from('>I', x, 4)[0]
        po = b + struct.unpack_from('>I', x, b + 24)[0]
        target = po + 8 + struct.unpack_from('>i', x, po + 8)[0]
        struct.pack_into('>i', x, po + 20, target - (po + 20))
        y, _ = self.convert(bytes(x))
        rows = read_nodes(y)[10]
        self.assertEqual(rows[S.msg_hash(b'a')][2], (1, 2, 3, 4))
        self.assertEqual(rows[S.msg_hash(b'b')][2], (1, 2, 3, 4))

    def test_null_pool_offsets_do_not_swap_neighboring_properties(self):
        ps = [prop('vector', 14, 0), prop('bool', 7, 0x01000000),
              prop('matrix', 15, 0), prop('text', 17, 0)]
        x = group([123], [(10, 0, [0, 1, 2, 3])], ps)
        y, _ = self.convert(x)
        rows = read_nodes(y)[10]
        self.assertIsNone(rows[S.msg_hash(b'vector')][2])
        self.assertIsNone(rows[S.msg_hash(b'matrix')][2])
        self.assertIsNone(rows[S.msg_hash(b'text')][2])
        self.assertEqual(rows[S.msg_hash(b'bool')][2], 1)

    def test_group_hash_recomputed(self):
        x = group([123], [(10, 0, [])], [], with_group=True)
        y, _ = self.convert(x)
        table = struct.unpack_from('<I', y, 16)[0]
        at = struct.unpack_from('<I', y, table)[0]
        self.assertEqual(struct.unpack_from('<I', y, at)[0], S.sdbm(struct.pack('<I', 123)))

    def test_checkpoint_fix_does_not_modify_shared_properties(self):
        schema = self.schema('TriggerAuto', [[16, 1, 'CMD_SetOptions'], [20, 7, 'bool'], [24, 3, 'short']])
        ps = [prop('CMD_SetOptions', 1, b'PERSIST\0', enum=0),
              prop('bool', 7, 0x01000000), prop('short', 3, 0x12340000)]
        x = group([123], [(0x8482720A, 0, [0, 1, 2]), (10, 0, [0, 1, 2])], ps)
        y, stats = self.convert(x, schema)
        rows = read_nodes(y)
        h = S.msg_hash(b'CMD_SetOptions')
        self.assertEqual(rows[0x8482720A][h][2], 0)
        self.assertEqual(rows[10][h][2], b'PERSIST')
        self.assertEqual(rows[10][S.msg_hash(b'bool')][2], 1)
        self.assertEqual(rows[10][S.msg_hash(b'short')][2], 0x1234)
        self.assertEqual(stats['auto_options'], 1)

    def test_relocated_table_keeps_backwards_struct_references(self):
        schema = self.schema('TriggerAuto', [[16, 1, 'CMD_SetOptions']])
        ps = [prop('CMD_SetOptions', 1, b'PERSIST\0', enum=0),
              prop('embedded', 22, ('node', 1)), prop('default_vector', 14, 0)]
        x = group([123], [(0x8482720A, 0, [0, 1, 2]), (10, 0, [])], ps)
        y, _ = self.convert(x, schema)
        rows = read_nodes(y)[0x8482720A]
        self.assertEqual(rows[S.msg_hash(b'embedded')][2], 10)
        self.assertIsNone(rows[S.msg_hash(b'default_vector')][2])

    def test_retarget_does_not_overwrite_shared_string(self):
        schema = self.schema('MultiManager', [[228, 17, 'CMD_SetTarget14']])
        ps = [prop('CMD_SetTarget14', 17, b'trig_box_drill_room_combat_wave_02\0')]
        x = group([123], [(0x3A73B1ED, 0, [0]), (10, 0, [0])], ps)
        y, stats = self.convert(x, schema)
        rows = read_nodes(y)
        h = S.msg_hash(b'CMD_SetTarget14')
        self.assertEqual(rows[0x3A73B1ED][h][2], b'enable_quarry_switch')
        self.assertEqual(rows[10][h][2], b'trig_box_drill_room_combat_wave_02')
        self.assertEqual(stats['retargeted'], 1)

    def test_missing_ragdoll_flag_property_added(self):
        schema = self.schema('RagdollComponent', [[16, 1, 'CMD_RagdollFlags']])
        x = group([123], [(0x4C8A721A, 0, []), (0xD6FBEF2C, 0, [])], [])
        y, stats = self.convert(x, schema)
        rows = read_nodes(y)
        h = S.msg_hash(b'CMD_RagdollFlags')
        self.assertEqual(rows[0x4C8A721A][h][2], 1)
        self.assertEqual(rows[0xD6FBEF2C][h][2], 9)
        self.assertEqual(stats['ragdoll_flags'], 2)

    def test_remapping_and_neutralisation(self):
        schema = self.schema('SaveKiosk')
        ps = [prop('ignored', 2, 1)]
        x = group([0x8F69BA55, 0x2B747EB6], [(10, 0, []), (11, 1, [0])], ps)
        y, stats = self.convert(x, schema)
        b = struct.unpack_from('<I', y, 4)[0]
        self.assertEqual(struct.unpack_from('<I', y, b + 0x20)[0], 123)
        self.assertEqual(struct.unpack_from('<I', y, b + 0x28)[0], 456)
        self.assertEqual(read_nodes(y)[11], {})
        self.assertEqual(stats['neutralised'], 1)

    def test_store_items_compacted_without_modifying_shared_guids(self):
        schema = self.schema('ItemStoreList')
        hidden = next(iter(S.STORE_HIDDEN))
        ps = [prop('items', 12, struct.pack('>4I', *hidden, 0, 0), index=0),
              prop('items', 12, struct.pack('>4I', 1, 2, 3, 4), index=1)]
        # An unrelated node shares both property rows and the GUID pool.
        schema[789] = {'name': 'Other', 'fields': [], 'size': 0, 'version': 1}
        x = group([123, 789], [(10, 0, [0, 1]), (11, 1, [0, 1])], ps)
        y, stats = self.convert(x, schema)
        b = struct.unpack_from('<I', y, 4)[0]
        no, po = struct.unpack_from('<I', y, b + 16)[0], struct.unpack_from('<I', y, b + 24)[0]

        def values(node):
            _, _, count, children = struct.unpack_from('<IHHI', y, b + no + 12 * node)
            result = []
            for pi in struct.unpack_from('<%dH' % count, y, b + children):
                at = b + po + 12 * pi + 8
                target = at + struct.unpack_from('<i', y, at)[0]
                result.append(struct.unpack_from('<4I', y, target))
            return result

        self.assertEqual(values(0), [(1, 2, 3, 4), (0, 0, 0, 0)])
        self.assertEqual(values(1), [(*hidden, 0, 0), (1, 2, 3, 4)])
        self.assertEqual(stats['store_items_hidden'], 1)

    def test_invalid_ranges_and_unknown_types_rejected(self):
        x = bytearray(group([123], [(10, 0, [0])], [prop('bad', 2, 1)]))
        b = struct.unpack_from('>I', x, 4)[0]
        struct.pack_into('>I', x, b + 24, len(x))
        with self.assertRaises(S.Unknown):
            self.convert(bytes(x))
        x = group([123], [(10, 0, [0])], [prop('bad', 0xFE, 0)])
        with self.assertRaises(S.Unknown):
            self.convert(x)

    def test_packed_path_still_works(self):
        head = bytearray(0x40)
        struct.pack_into('>I', head, 4, 0x40)
        x = head + struct.pack('>IIIHHII', S.BLOCK, 24, 24, 0, 0, 0, 24)
        y, stats = self.convert(x)
        self.assertEqual(struct.unpack_from('<I', y, 0x40)[0], S.BLOCK)
        self.assertNotIn('property_tree', stats)


if __name__ == '__main__':
    unittest.main()
