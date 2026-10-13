"""Exact embedded texture bytes, UV/material bindings and retained room/lights."""
import argparse,hashlib,json,struct
from pathlib import Path
from PIL import Image

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(a):
 raw=(a.assets/'flagship.glb').read_bytes();magic,version,total=struct.unpack_from('<4sII',raw);assert (magic,version,total)==(b'glTF',2,len(raw))
 size,kind=struct.unpack_from('<II',raw,12);assert kind==0x4E4F534A;d=json.loads(raw[20:20+size]);pos=20+size;blen,bkind=struct.unpack_from('<II',raw,pos);assert bkind==0x004E4942
 binary=raw[pos+8:pos+8+blen];rows=[]
 for i in d.get('images',[]):
  assert 'uri' not in i;v=d['bufferViews'][i['bufferView']];data=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
  assert data[:8]==b'\x89PNG\r\n\x1a\n';width,height=struct.unpack_from('>II',data,16)
  matches=[root/'textures'/(i['name']+'.png') for root in (a.bridge,a.bake) if (root/'textures'/(i['name']+'.png')).exists()]
  assert len(matches)==1 and data==matches[0].read_bytes(),'Missing, ambiguous or altered baked image'
  with Image.open(matches[0]) as im:extrema=im.convert('RGB').getextrema()
  rows.append({'name':i['name'],'size':[width,height],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'channel_extrema':extrema})
 mats=[(i,m) for i,m in enumerate(d['materials']) if 'baseColorTexture' in m.get('pbrMetallicRoughness',{})]
 assert len(rows)==9 and len(mats)==3
 assert sum(r['name'].startswith('fore09-service-') for r in rows)==3
 for i,m in mats:
  assert 'metallicRoughnessTexture' in m['pbrMetallicRoughness'] and 'normalTexture' in m
  for mesh in d['meshes']:
   for prim in mesh['primitives']:
    if prim['material']==i:assert 'TEXCOORD_0' in prim['attributes']
 retained={name:(a.assets/name).read_bytes()==(a.previous/name).read_bytes() for name in ('archive.glb','service-lights.glb','service-lighting.mjs')};assert all(retained.values())
 profile=json.loads((a.assets/'service-lighting.json').read_text());assert profile['model_sha256']==sha(a.assets/'flagship.glb') and profile['browser_tested'] is False
 r={'passed':True,'flagship_sha256':sha(a.assets/'flagship.glb'),'embedded_images':rows,'textured_materials':[m['name'] for i,m in mats],'retained_byte_identical':retained,'lighting_model_pin_valid':True,'browser_tested':False,
  'estimated_rgba8_texture_mib_with_mips':sum(x['size'][0]*x['size'][1]*4*4/3 for x in rows)/1024**2}
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--bake',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
