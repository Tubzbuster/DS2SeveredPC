"""Patch only the actual SP11SaveSlot movie; never renumber save chapters."""
from pathlib import Path
import struct,json,sys,hashlib,zlib
import argparse
parser=argparse.ArgumentParser(description='Build the two-chapter save preview delta from your own original PC files and PS3 chapter icons.')
parser.add_argument('--archive',type=Path,required=True,help='Original PC DS2DAT6.DAT')
parser.add_argument('--chapter1',type=Path,required=True)
parser.add_argument('--chapter2',type=Path,required=True)
parser.add_argument('--research-tools',type=Path,required=True,help='Upstream source/tools/research directory')
parser.add_argument('--output',type=Path,required=True,help='Private output directory; never commit generated game data')
args=parser.parse_args();sys.stdout.reconfigure(encoding='utf-8');M=A=args.output;A.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(args.research_tools))
from ds2 import bigarchive,streamfile,streamwrite,toc,saveicons
from PIL import Image,ImageOps
u=lambda b,p:struct.unpack_from('<I',b,p)[0]
put=lambda b,p,v:struct.pack_into('<I',b,p,v)
sha=lambda b:hashlib.sha256(b).hexdigest()
with args.archive.open('rb') as f:
 idx,_=bigarchive.read_index(f);off,size=idx[bigarchive.name_hash('frontend\\frontend.str')];f.seek(off);raw=f.read(size)
original=next(x.payload() for x in streamfile.read(raw)[1] if x.type=='APX' and x.name=='sp11saveslot.apx')
assert sha(original)=='dcc335c2234decbda5199c559f9247d14edd8d0ebd0cad6dcea669361111b2f4', 'Unsupported source APX'
chunks=[];p=8
while p<len(original):
 n=u(original,p+4);assert n>=8 and p+n<=len(original);chunks.append((original[p:p+4],original[p+8:p+n]));p+=n
apt=bytearray(next(b for t,b in chunks if t==b'itpa'));const=next(b for t,b in chunks if t==b'snoc');root=u(const,20);assert u(apt,root)==9
nt=u(apt,root+20);table=u(apt,root+24);assert nt==158
chars=[u(apt,table+i*4) for i in range(nt)];sprite=chars[113];nf=u(apt,sprite+8);frames=u(apt,sprite+12);assert nf==18
geom=bytearray(next(b for t,b in chunks if t==b'ibur'));p=0;records={}
while p<len(geom):
 i=u(geom,p);n=u(geom,p+4);assert n>=8;records[i]=(p,n);p+=n
assert p==len(geom)
# Page 2 grows downwards. Original compressed blocks stay byte-exact. Halve
# only page-2 V coefficients: the old top half samples the same old pixels.
for i,(p,n) in records.items():
 if n==104 and u(geom,p+0x3c)==2:
  for k in (0x2c,0x30,0x34):struct.pack_into('<f',geom,p+k,struct.unpack_from('<f',geom,p+k)[0]*.5)
# New PS3 source art occupies two 256x128 tiles, aspect preserved.
canvas=Image.new('RGBA',(1024,128),(0,0,0,255))
for chapter in (1,2):
 im=Image.open(args.chapter1 if chapter==1 else args.chapter2).convert('RGBA')
 fit=ImageOps.contain(im,(256,128),Image.Resampling.LANCZOS);canvas.paste(fit,((chapter-1)*256+(256-fit.width)//2,(128-fit.height)//2))
canvas.save(M/'apx-added-atlas.png')
px=[[canvas.getpixel((x,y)) for x in range(1024)] for y in range(128)];extra=saveicons.dxt5(px,1024,128);assert len(extra)==131072
shape_template=bytes(apt[chars[80]:chars[80]+28]);bitmap_template=bytes(apt[chars[79]:chars[79]+12]);assert u(shape_template,0)==1 and u(shape_template,24)==80 and u(bitmap_template,0)==7
new_shapes=[]
for chapter in (1,2):
 bitmap_id=len(chars);chars.append(len(apt));bitmap=bytearray(bitmap_template);put(bitmap,8,bitmap_id);apt.extend(bitmap)
 shape_id=len(chars);chars.append(len(apt));shape=bytearray(shape_template);put(shape,24,shape_id);apt.extend(shape);new_shapes.append(shape_id)
 p,n=records[80];g=bytearray(geom[p:p+n]);put(g,0,shape_id)
 for k,v in [(0x1c,256/133.99/1024),(0x20,0),(0x24,(chapter-1)*.25+.99*256/133.99/1024),(0x2c,0),(0x30,128/67/256),(0x34,.5-.5*128/67/256)]:struct.pack_into('<f',g,k,v)
 geom.extend(g)
old_frames=bytes(apt[frames:frames+nf*8]);new_frame_entries=[]
for ch in new_shapes:
 # Clone the last ordinary preview placement, preserving depth/border.
 last=frames+(nf-1)*8;assert u(apt,last)==1;control=u(apt,u(apt,last+4));new_control=bytearray(apt[control:control+64]);assert u(new_control,0)==3 and u(new_control,4)==3 and u(new_control,8)==1
 put(new_control,12,ch);control_off=len(apt);apt.extend(new_control);controls_off=len(apt);apt.extend(struct.pack('<I',control_off));new_frame_entries.append(struct.pack('<II',1,controls_off))
new_frames_off=len(apt);apt.extend(old_frames+b''.join(new_frame_entries));put(apt,sprite+8,nf+2);put(apt,sprite+12,new_frames_off)
for cid,ptr in enumerate(chars):
 if ptr and u(apt,ptr)==7:assert u(apt,ptr+8)==cid, ("bitmap.zID must equal character index",cid)
 if ptr and u(apt,ptr)==1:assert u(apt,ptr+24)==cid, ("shape geometry ID must equal character index",cid)
new_chars_off=len(apt);apt.extend(struct.pack('<%dI'%len(chars),*chars));put(apt,root+20,len(chars));put(apt,root+24,new_chars_off)
th=bytearray(next(b for t,b in chunks if t==b'h4xt'));assert struct.unpack_from('<H',th,6)[0]==2;desc=u(th,12)+24;assert u(th,desc+4)==131072 and struct.unpack_from('<HH',th,desc+8)==(1024,128)
put(th,desc+4,262144);struct.pack_into('<H',th,desc+10,256)
new_chunks=[];tex=0
for t,b in chunks:
 if t==b'gila':continue
 if t==b'itpa':b=bytes(apt)
 elif t==b'ibur':b=bytes(geom)
 elif t==b'h4xt':b=bytes(th)
 elif t==b't4xt':
  tex+=1
  if tex==2:b+=extra
 new_chunks.append((t,b))
out=bytearray(b'fxpa'+bytes(4))
for t,b in new_chunks:
 if (len(out)+8)%16:
  pad=(-(len(out)+8))%16
  if pad<8:pad+=16
  out+=b'gila'+struct.pack('<I',pad)+bytes(pad-8)
 out+=t+struct.pack('<I',len(b)+8)+b
put(out,4,len(out));modified=bytes(out);(M/'sp11saveslot.patched.apx').write_bytes(modified)
# Repack the one original stream, validating every other asset payload.
with args.archive.open('rb') as f:
 idx,_=bigarchive.read_index(f)
 def read(name):
  o,n=idx[bigarchive.name_hash(name)];f.seek(o);return f.read(n)
 source=read('frontend\\frontend.str');table_original=read('frontend\\frontend.toc')
assets=streamfile.read(source)[1];w=streamwrite.Writer();hits=0
for a in assets:
 b=a.payload()
 if a.type=='APX' and a.name=='sp11saveslot.apx':assert b==original;b=modified;hits+=1
 if a.type=='APX' and a.name=='sp11saveslot.apx':w.add(a.type_hash,a.flags,a.ids,a.name,a.path,a.type,b)
 else:
  w._put(a.header)
  for _,chunk in a.chunks:w._put(chunk)
assert hits==1
result=w.data();newassets=streamfile.read(result)[1];assert len(newassets)==len(assets)
for a,b in zip(assets,newassets):
 assert (a.ids,a.type,a.name,a.path)==(b.ids,b.type,b.name,b.path)
 assert b.payload()==(modified if a.type=='APX' and a.name=='sp11saveslot.apx' else a.payload())
new_toc=toc.set_size(table_original,'frontend\\frontend',sum(a.usize for a in assets)+len(modified)-len(original))
(M/'frontend.patched.str').write_bytes(result);(A/'SaveIcons.toc.bin').write_bytes(new_toc)
# Conservative COPY/INSERT delta; offsets refer only to the verified original.
block=1024;index={}
for i in range(0,len(source)-16,block):index.setdefault(source[i:i+16],[]).append(i)
p=0;literal=bytearray();delta=bytearray(b'DS2APX1\0'+struct.pack('<II',len(source),len(result)));copies=0
while p<len(result):
 best=0;at=0
 for old in index.get(result[p:p+16],[])[:20]:
  length=16;limit=min(len(source)-old,len(result)-p)
  while length+4096<=limit and source[old+length:old+length+4096]==result[p+length:p+length+4096]:length+=4096
  while length<limit and source[old+length]==result[p+length]:length+=1
  if length>best:best=length;at=old
 if best>=64:
  if literal:delta+=b'\1'+struct.pack('<I',len(literal))+literal;literal.clear()
  delta+=b'\0'+struct.pack('<II',at,best);copies+=1;p+=best
 else:literal.append(result[p]);p+=1
if literal:delta+=b'\1'+struct.pack('<I',len(literal))+literal
# Uncompressed, strict bounded recipe; resource compression is optional.
delta+=b'\xff';(A/'SaveIcons.tail.bin').write_bytes(delta)
archive=M/'DS2DAT3.apx.expected.DAT';bigarchive.write(str(archive),[('frontend\\frontend.str',result),('frontend\\frontend.toc',new_toc)])
report=dict(status='OFFLINE_APX_PATCH_ONLY_NOT_YET_GAME_TESTED',source_stream_sha256=sha(source),source_toc_sha256=sha(table_original),source_stream_bytes=len(source),output_stream_sha256=sha(result),output_stream_bytes=len(result),archive_sha256=sha(archive.read_bytes()),archive_bytes=archive.stat().st_size,apx_original_sha256=sha(original),apx_patched_sha256=sha(modified),old_frames=18,new_frames=20,new_shape_ids=new_shapes,native_preview_indices=[18,19],source_art_original=True,aspect_preserved=True,original_texture_blocks_unchanged=True,all_other_asset_payloads_unchanged=True,save_files_untouched=True,delta_bytes=len(delta),copy_instructions=copies)
(M/'apx-patch.json').write_text(json.dumps(report,indent=2),encoding='utf-8');(A/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
