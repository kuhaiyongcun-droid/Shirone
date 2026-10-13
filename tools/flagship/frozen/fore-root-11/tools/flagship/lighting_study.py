"""Add reversible ship-fixed lighting to verified surface06. No mesh changes."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f
from surface_gate import require
from surface_finish import sha
DEFAULT=Path(__file__).with_name('lighting-study-07.json')
def build(a):
 cfg=json.loads(a.config.read_text());require(a.source,a.validation)
 assert sha(a.source)==cfg['source_sha256'] and not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));f.PREFIX=cfg['prefix'];before=f.protected()
 col=bpy.data.collections.new(cfg['collection']);bpy.context.scene.collection.children.link(col)
 for light in cfg['lights']:
  name=cfg['prefix']+light['name'];data=bpy.data.lights.new(name,'SPOT');o=bpy.data.objects.new(name,data);col.objects.link(o)
  o.location=light['position'];o.rotation_euler=(Vector(light['target'])-o.location).to_track_quat('-Z','Y').to_euler()
  data.energy=light['energy_w'];data.color=light['color_linear'];data.spot_size=math.radians(light['cone_degrees']);data.spot_blend=light['blend']
  data.shadow_soft_size=light['radius'];data.use_shadow=light['cast_shadow'];o['role']='service_bay_light';o['ship_fixed']=True
  o['fixture']=light['fixture'] or 'art-directed reflected fill';o['target']=json.dumps(light['target'])
 bpy.context.view_layer.update();assert f.protected()==before,'Original geometry/materials/lights/cameras changed'
 scene=bpy.context.scene;scene.name='KUHAI — Service Lighting 07';scene['revision']=cfg['revision'];scene['lighting_config_sha256']=sha(a.config)
 scene.camera=bpy.data.objects['side03_context'];a.output.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file;p=a.output.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 r={'revision':cfg['revision'],'input_sha256':sha(a.source),'source_sha256':sha(a.output),'config_sha256':sha(a.config),'new_lights':len(cfg['lights']),
    'geometry_changes':False,'materials_changed':False,'existing_lights_changed':False,'browser_tested':False,'published':False}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);build(p.parse_args())
