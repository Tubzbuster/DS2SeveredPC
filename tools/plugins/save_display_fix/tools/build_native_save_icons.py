"""Add native previews while preserving the original icon mappings.

This uses private game/art inputs and emits private resources, never PR data.
"""
from pathlib import Path
import argparse,sys,struct,json,hashlib,zlib
from PIL import Image,ImageOps
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--frontend-overlay',type=Path,required=True)
p.add_argument('--chapter1',type=Path,required=True)
p.add_argument('--chapter2',type=Path,required=True)
p.add_argument('--research-tools',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args();sys.path.insert(0,str(args.research_tools))
from ds2 import bigarchive,streamfile,streamwrite,toc,saveicons
from native_table_refs import append_icon_references
sha=lambda b:hashlib.sha256(b).hexdigest()
out=args.output;out.mkdir(parents=True,exist_ok=False)
def read(archive,name):
 with archive.open('rb') as f:
  idx,_=bigarchive.read_index(f);off,size=idx[bigarchive.name_hash(name)];f.seek(off);return f.read(size)
name='global_assets\\global_assets'
source=read(args.archive,name+'.str');table=read(args.archive,name+'.toc')
assets=streamfile.read(source)[1]
table_report=None;mapping_growth=0
additions=[]
for chapter,ch in [(1,17),(2,18)]:
 image=Image.open(args.chapter1 if chapter==1 else args.chapter2).convert('RGBA')
 canvas=Image.new('RGBA',(128,64),(0,0,0,255));fit=ImageOps.contain(image,(128,64),Image.Resampling.LANCZOS);canvas.paste(fit,((128-fit.width)//2,(64-fit.height)//2));png=out/f'chapter{chapter}.png';canvas.save(png)
 for a in assets:
  payload=a.payload()
  if a.type=='VFX' and a.name==saveicons.TEMPLATE_VFX:
   ids=(a.ids[0],)+saveicons._guid(ch)
   entry=(a.type_hash,a.flags,ids,a.name.replace('01',str(ch)),a.path.replace('icn01','icn%d'%ch),a.type,saveicons._vfx(payload,ch))
  elif a.type in ('tg4h','tg4d') and a.name==saveicons.TEMPLATE_TEX:
   newname=saveicons.TEMPLATE_TEX.replace('ch01','ch%d'%ch)
   ids=a.ids[:4]+(zlib.crc32(newname.encode(),zlib.crc32(saveicons.TEX_FOLDER)),)
   if a.type=='tg4h':
    # The internal texture key must agree with its SHDR key. Original ch01
    # and ch02 headers differ only at this key and the trailing name.
    assert struct.unpack_from('<I',payload,0x14)[0]==a.ids[-1]
    replacement=bytearray(payload.replace(saveicons.TEMPLATE_TEX.encode(),newname.encode()))
    struct.pack_into('<I',replacement,0x14,ids[-1])
    replacement=bytes(replacement)
    assert struct.unpack_from('<I',replacement,0x14)[0]==ids[-1]
   else:replacement=saveicons.texture_data(png.read_bytes())
   assert len(replacement)==len(payload)
   entry=(a.type_hash,a.flags,ids,newname,a.path.replace('ch01','ch%d'%ch),a.type,replacement)
  else:continue
  assert not any(tuple(old.ids)==tuple(ids) for old in assets),'ID already exists'
  additions.append(entry)
assert len(additions)==6
w=streamwrite.Writer()
for a in assets:
 if a.type=='SimGroup' and a.path.lower()==saveicons.TABLE_PATH:
  # Preserve the original stream convention: all picture resources precede
  # the terminal SimGroup. Existing object records and mappings remain intact.
  for entry in additions:w.add(*entry)
  payload,table_report=append_icon_references(a.payload(),[saveicons._guid(ch) for ch in (17,18)],saveicons.sdbm)
  mapping_growth=len(payload)-a.usize;w.add(a.type_hash,a.flags,a.ids,a.name,a.path,a.type,payload)
 else:
  w._put(a.header)
  for _,chunk in a.chunks:w._put(chunk)
assert table_report is not None
result=w.data()
modified=streamfile.read(result)[1];assert len(modified)==len(assets)+6
assert modified[-1].type=='SimGroup'
by_ids={tuple(a.ids):a for a in modified}
for before in assets:
 after=by_ids[tuple(before.ids)]
 if not(before.type=='SimGroup' and before.path.lower()==saveicons.TABLE_PATH):assert before.payload()==after.payload()
table2=toc.set_size(table,name,sum(a.usize for a in assets)+mapping_growth+sum(len(e[-1]) for e in additions))
(out/'NativeSaveIcons.toc.bin').write_bytes(table2)
index={}
for i in range(0,len(source)-16,1024):index.setdefault(source[i:i+16],[]).append(i)
p=0;literal=bytearray();recipe=bytearray(b'DS2APX1\0'+struct.pack('<II',len(source),len(result)))
while p<len(result):
 best=0;at=0
 for old in index.get(result[p:p+16],[])[:20]:
  length=16;limit=min(len(source)-old,len(result)-p)
  while length+4096<=limit and source[old+length:old+length+4096]==result[p+length:p+length+4096]:length+=4096
  while length<limit and source[old+length]==result[p+length]:length+=1
  if length>best:best=length;at=old
 if best>=64:
  if literal:recipe+=b'\1'+struct.pack('<I',len(literal))+literal;literal.clear()
  recipe+=b'\0'+struct.pack('<II',at,best);p+=best
 else:literal.append(result[p]);p+=1
if literal:recipe+=b'\1'+struct.pack('<I',len(literal))+literal
recipe+=b'\xff';recipe=bytes(recipe)
(out/'NativeSaveIcons.tail.bin').write_bytes(recipe)
files=[(n,read(args.frontend_overlay,n)) for n in ['frontend\\frontend.str','frontend\\frontend.toc']]
files += [(name+'.str',result),(name+'.toc',table2)]
archive=out/'DS2DAT3.combined.DAT';bigarchive.write(str(archive),files)
report={'source_sha256':sha(source),'source_toc_sha256':sha(table),'source_bytes':len(source),'result_sha256':sha(result),'result_bytes':len(result),'recipe_sha256':sha(recipe),'recipe_bytes':len(recipe),'toc_sha256':sha(table2),'toc_bytes':len(table2),'archive_sha256':sha(archive.read_bytes()),'archive_bytes':archive.stat().st_size,'native_guids':[list(saveicons._guid(ch)) for ch in (17,18)],'only_original_asset_with_new_fields':'global_assets.simgroup.bin','other_original_assets_unchanged':True,'icon_table':table_report,'saves_untouched':True,'gameplay_validated':False}
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
