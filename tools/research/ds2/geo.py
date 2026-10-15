"""Mesh ('MGAE' PC / 'EAGM' 360) structure, both byte orders.

Field layout from the PC mesh as documented by the DS1-3 Modding Toolkit
(4Kodda) GEO importer/exporter: header pointers, DataTable1 (one 0xC0-byte
entry per draw table), DataTable2 (buffer descriptors), local UV offset at
0x9C. Our own implementation; offsets only.
"""
import struct

DT1_ENTRY = 0xC0


class Table:
    pass


def parse(d, be):
    E = '>' if be else '<'
    u32 = lambda o: struct.unpack_from(E + 'I', d, o)[0]
    i32 = lambda o: struct.unpack_from(E + 'i', d, o)[0]
    u16 = lambda o: struct.unpack_from(E + 'H', d, o)[0]
    g = Table()
    g.be = be
    g.magic = d[:4]
    g.version = u32(4)
    g.platform = u32(8)
    g.model_name_offset = u32(0x20)
    g.table_count = i32(0x34)
    g.data_table1 = u32(0x50)
    g.geom_end = i32(0x60)
    g.data_table2 = u32(0x68)
    g.local_uv_offset = u32(0x9C)
    g.tables = []
    for i in range(g.table_count):
        o = g.data_table1 + DT1_ENTRY * i
        t = Table()
        t.entry = o
        t.name_offset = u32(o)
        t.table_offset = u32(o + 0x20)
        t.always14 = d[o + 0x26] if be else d[o + 0x26]
        t.uv_size = d[o + 0x27]
        t.palette_count = d[o + 0x25]
        t.face_count = i32(o + 0x30)
        t.vert_count = u16(o + 0x38)
        t.lod_type = u16(o + 0x3C)
        t.bone_palette_offset = u32(o + 0x44)
        t.vert_size = i32(o + 0x64)
        t.vert_id = i32(o + 0x6C)
        t.vert_offset = u32(o + 0x84)
        t.face_offset = u32(o + 0x88)
        g.tables.append(t)
    g.dt2 = []
    o = g.data_table2
    while o + 16 <= len(d):
        size, count = u32(o), u32(o + 4)
        flags = d[o + 8:o + 12]
        ptr = u32(o + 12)
        if size == 0 and count == 0 and ptr == 0:
            break
        g.dt2.append((size, count, flags, ptr))
        o += 16
        if len(g.dt2) > 64:
            break
    return g
