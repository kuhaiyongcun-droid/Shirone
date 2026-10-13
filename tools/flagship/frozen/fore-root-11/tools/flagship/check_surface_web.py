"""Verify embedded PBR bytes, texture UVs, GLB structure and archive isolation."""
import argparse,hashlib,json,struct
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(a):
 raw=(a.assets/'flagship.glb').read_bytes();magic,version,total=struct.unpack_from('<4sII',raw)
 assert (magic,version,total)==(b'glTF',2,len(raw))
 size,kind=struct.unpack_from('<II',raw,12);assert kind==0x4E4F534A
 d=json.loads(raw[20:20+size]);pos=20+size;blen,bkind=struct.unpack_from('<II',raw,pos);assert bkind==0x004E4942
 binary=raw[pos+8:pos+8+blen];rows=[]
 for i in d.get('images',[]):
  assert 'uri' not in i
  v=d['bufferViews'][i['bufferView']];data=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
  assert data[:8]==b'\x89PNG\r\n\x1a\n';width,height=struct.unpack_from('>II',data,16)
  expected=a.bake/'textures'/(i['name']+'.png');assert data==expected.read_bytes(),'Texture changed during export'
  rows.append({'name':i['name'],'size':[width,height],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 mats=[(i,m) for i,m in enumerate(d['materials']) if 'baseColorTexture' in m.get('pbrMetallicRoughness',{})]
 assert len(rows)==6 and len(mats)==2
 for i,m in mats:
  assert 'metallicRoughnessTexture' in m['pbrMetallicRoughness'] and 'normalTexture' in m
  for mesh in d['meshes']:
   for prim in mesh['primitives']:
    if prim['material']==i:assert 'TEXCOORD_0' in prim['attributes']
 assert (a.assets/'archive.glb').read_bytes()==a.previous_archive.read_bytes()
 r={'passed':True,'embedded_images':rows,'textured_materials':[m['name'] for i,m in mats],
    'archive_byte_identical':True,'browser_tested':False,
    'estimated_rgba8_texture_mib_with_mips':sum(x['size'][0]*x['size'][1]*4*4/3 for x in rows)/1024**2}
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--bake',type=Path,required=True)
 p.add_argument('--previous-archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
