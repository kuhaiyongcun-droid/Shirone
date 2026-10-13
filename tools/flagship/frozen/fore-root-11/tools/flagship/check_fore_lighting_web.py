"""Keep all nine existing PBR atlases and the archive byte-identical."""
import argparse,hashlib,json,struct
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def images(path):
 raw=path.read_bytes();magic,version,total=struct.unpack_from('<4sII',raw);assert (magic,version,total)==(b'glTF',2,len(raw));size,kind=struct.unpack_from('<II',raw,12);assert kind==0x4e4f534a
 d=json.loads(raw[20:20+size]);pos=20+size;length,kind=struct.unpack_from('<II',raw,pos);assert kind==0x004e4942;binary=raw[pos+8:pos+8+length];rows={}
 for i in d.get('images',[]):
  assert 'uri' not in i;v=d['bufferViews'][i['bufferView']];data=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];rows[i['name']]=hashlib.sha256(data).hexdigest()
 for mi,m in enumerate(d['materials']):
  if 'baseColorTexture' not in m.get('pbrMetallicRoughness',{}):continue
  assert 'normalTexture' in m and 'metallicRoughnessTexture' in m['pbrMetallicRoughness']
  for mesh in d['meshes']:
   for p in mesh['primitives']:
    if p['material']==mi:assert 'TEXCOORD_0' in p['attributes']
 return rows
def main(a):
 old=images(a.previous/'flagship.glb');new=images(a.assets/'flagship.glb');assert old==new and len(new)==9
 assert (a.previous/'archive.glb').read_bytes()==(a.assets/'archive.glb').read_bytes()
 profile=json.loads((a.assets/'service-lighting.json').read_text());assert profile['model_sha256']==sha(a.assets/'flagship.glb') and profile['lights_sha256']==sha(a.assets/'service-lights.glb')
 r={'passed':True,'flagship_sha256':sha(a.assets/'flagship.glb'),'prior_sha256':sha(a.previous/'flagship.glb'),'embedded_texture_sha256':new,'all_nine_atlases_unchanged':True,'archive_byte_identical':True,'light_profile_bound_to_model':True,'browser_tested':False}
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
