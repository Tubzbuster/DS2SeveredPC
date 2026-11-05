"""Append native in-game previews; leave all original global assets intact.

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
sha=lambda b:hashlib.sha256(b).hexdigest()
out=args.output;out.mkdir(parents=True,exist_ok=False)
def read(archive,name):
 with archive.open('rb') as f:
  idx,_=bigarchive.read_index(f);off,size=idx[bigarchive.name_hash(name)];f.seek(off);return f.read(size)
name='global_assets\\global_assets'
source=read(args.archive,name+'.str');table=read(args.archive,name+'.toc')
assets=streamfile.read(source)[1]
w=streamwrite.Writer();w.out=bytearray(source)
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
   replacement=payload.replace(saveicons.TEMPLATE_TEX.encode(),newname.encode()) if a.type=='tg4h' else saveicons.texture_data(png.read_bytes())
   assert len(replacement)==len(payload)
   entry=(a.type_hash,a.flags,ids,newname,a.path.replace('ch01','ch%d'%ch),a.type,replacement)
  else:continue
  assert not any(tuple(old.ids)==tuple(ids) for old in assets),'ID already exists'
  w.add(*entry);additions.append(entry)
assert len(additions)==6
result=w.data();assert result[:len(source)]==source
modified=streamfile.read(result)[1];assert len(modified)==len(assets)+6
for before,after in zip(assets,modified):
 assert before.ids==after.ids and before.payload()==after.payload()
table2=toc.set_size(table,name,sum(a.usize for a in assets)+sum(len(e[-1]) for e in additions))
(out/'NativeSaveIcons.toc.bin').write_bytes(table2)
tail=result[len(source):]
recipe=b'DS2APX1\0'+struct.pack('<II',len(source),len(result))+b'\0'+struct.pack('<II',0,len(source))+b'\1'+struct.pack('<I',len(tail))+tail+b'\xff'
(out/'NativeSaveIcons.tail.bin').write_bytes(recipe)
files=[(n,read(args.frontend_overlay,n)) for n in ['frontend\\frontend.str','frontend\\frontend.toc']]
files += [(name+'.str',result),(name+'.toc',table2)]
archive=out/'DS2DAT3.combined.DAT';bigarchive.write(str(archive),files)
report={'source_sha256':sha(source),'source_toc_sha256':sha(table),'source_bytes':len(source),'result_sha256':sha(result),'result_bytes':len(result),'recipe_sha256':sha(recipe),'recipe_bytes':len(recipe),'toc_sha256':sha(table2),'toc_bytes':len(table2),'archive_sha256':sha(archive.read_bytes()),'archive_bytes':archive.stat().st_size,'native_guids':[list(saveicons._guid(ch)) for ch in (17,18)],'all_original_assets_unchanged':True,'saves_untouched':True,'gameplay_validated':False}
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
