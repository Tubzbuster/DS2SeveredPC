"""Add two supported icon-table fields without changing existing mappings.

The original UIMenuCheckpointIcons class has 60 named slots, of which this
supported global SimGroup uses 18. The additional preview references use supported spare fields; every
original mapping and resolved property value is retained.
"""
import struct

def append_icon_references(data, guids, name_hash):
    assert len(guids)==2
    u=lambda b,p:struct.unpack_from('<I',b,p)[0]
    base=u(data,4)
    assert u(data,base)==0x91C8773C and base+u(data,base+4)==len(data)
    types,type_count,nodes,node_count,properties,property_count=struct.unpack_from('<6I',data,base+8)
    property_end=base+properties+property_count*12
    icon_types=[i for i in range(type_count) if u(data,base+types+i*8)==name_hash('UIMenuCheckpointIcons')]
    assert len(icon_types)==1
    icon_nodes=[]
    for i in range(node_count):
        at=base+nodes+i*12
        _,kind,count,children=struct.unpack_from('<IHHI',data,at)
        if kind==icon_types[0]:icon_nodes.append((at,count,children))
    assert len(icon_nodes)==1
    node_at,count,children=icon_nodes[0]
    assert count==36
    old_children=list(struct.unpack_from('<36H',data,base+children))
    assert u(data,base+properties+old_children[0]*12)==name_hash('CMD_SetChkpntIcon1Name')
    names={u(data,base+properties+i*12) for i in old_children}
    free_slots=[slot for slot in range(1,61) if all(name_hash(f'CMD_SetChkpntIcon{slot}{kind}') not in names for kind in ('Name','VFX'))]
    assert len(free_slots)>=2
    new_slots=free_slots[:2]
    # Insert four records before the trailing child/string/GUID pools. All
    # old scalar properties retain their bits; all old references retain
    # their resolved bytes after the pool moves by exactly 48 bytes.
    growth=48
    out=bytearray(data[:property_end]+bytes(growth)+data[property_end:])
    old_refs=[]
    for i in range(property_count):
        p=base+properties+i*12
        count,kind,index=struct.unpack_from('<HBB',data,p+4)
        pointer=count!=0xFFFF or kind in (12,13,14,15,16,17)
        relative=struct.unpack_from('<i',data,p+8)[0]
        if pointer and relative:
            target=p+8+relative
            assert property_end<=target<len(data)
            struct.pack_into('<i',out,p+8,relative+growth)
            assert out[target+growth:target+growth+min(16,len(data)-target)]==data[target:target+min(16,len(data)-target)]
            old_refs.append(i)
    for i in range(node_count):
        p=base+nodes+i*12
        _,_,n,ptr=struct.unpack_from('<IHHI',data,p)
        if n:
            assert property_end<=base+ptr and base+ptr+n*2<=len(data)
            struct.pack_into('<I',out,p+8,ptr+growth)
            assert out[base+ptr+growth:base+ptr+growth+n*2]==data[base+ptr:base+ptr+n*2]
    out+=bytes(-len(out)%4)
    guid_positions=[]
    for guid in guids:guid_positions.append(len(out));out+=struct.pack('<4I',*guid)
    for i,(slot,guid_at) in enumerate(zip(new_slots,guid_positions)):
        p=property_end+i*24
        struct.pack_into('<III',out,p,name_hash(f'CMD_SetChkpntIcon{slot}Name'),0xFF0AFFFF,name_hash(f'severed_ch0{i+1}'))
        struct.pack_into('<III',out,p+12,name_hash(f'CMD_SetChkpntIcon{slot}VFX'),0xFF0CFFFF,guid_at-(p+20))
    new_children=old_children+list(range(property_count,property_count+4))
    child_at=len(out);out+=struct.pack('<40H',*new_children)
    struct.pack_into('<H',out,node_at+6,40)
    struct.pack_into('<I',out,node_at+8,child_at-base)
    struct.pack_into('<I',out,base+28,property_count+4)
    struct.pack_into('<I',out,base+4,len(out)-base)
    assert out[:base]==data[:base]
    for i in range(property_count):
        p=base+properties+i*12
        assert out[p:p+8]==data[p:p+8]
        if i not in old_refs:assert out[p+8:p+12]==data[p+8:p+12]
    return bytes(out),{'original_properties':property_count,'new_properties':property_count+4,'original_icon_fields':36,'new_icon_fields':40,'added_parameter_slots':new_slots,'old_references_relocated':len(old_refs),'existing_icon_mappings_preserved':True,'original_object_records_preserved':True}
