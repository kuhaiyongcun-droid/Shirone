"""Ship-mounted fore10 task fixtures; preserve every prior scene datablock."""
import argparse,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_scene as base
import finish_study as f
from fore_surface_check import require as input_require
from surface_finish import sha
DEFAULT=Path(__file__).with_name('fore-lighting-10.json')
INPUT='23df549788eb4e29b2394fd6529c7cb8c0602092273c264b3385923dbfe073f3'
P='FORE10 / ';FIX='FORE10_FIXTURES';LIGHTS='FORE10_LIGHTS'
def attach(o,target,point):
 o['fixture_attachment_target']=target;o['fixture_attachment_point']=json.dumps(point);return o
def build(a):
 input_require(a.source,a.validation);cfg=json.loads(a.config.read_text());assert sha(a.source)==INPUT==cfg['source_sha256'] and not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));f.PREFIX=P;before=f.protected()
 base.COLLECTIONS.update({c.name:c for c in bpy.data.collections});base.collection(FIX);base.collection(LIGHTS)
 for key,oldname in (('case','casing'),('metal','metal')):
  m=bpy.data.materials['FORE09 / '+oldname].copy();m.name=P+key;base.MATERIALS[key]=m
 lens=base.material(P+'diffuser',(.64,.59,.46),.0,.47,emission=1.8)
 base.MATERIALS['lens']=lens
 wall='FORE09 / Outboard continuous sill'
 for d in cfg['fixtures']:
  x=d['x'];fid=d['id'];name=P+fid+' / '
  mount=base.box(name+'wall shoe',(x,-82.51,24.96),(1.35,.16,.45),'case',FIX,.035)
  attach(mount,wall,(x,-82.56,24.96))
  body=base.box(name+'shielded housing',(x,-82.28,24.92),(1.55,.46,.40),'case',FIX,.045)
  attach(body,mount.name,(x,-82.47,24.96))
  emitter=base.box(name+'inset downward diffuser',(x,-82.21,24.715),(1.12,.31,.05),'lens',FIX,.018)
  attach(emitter,body.name,(x,-82.21,24.735))
  gland=base.cylinder(name+'sealed rear feed',(x,-82.60,24.96),.095,.40,'metal','Y',FIX,vertices=20)
  attach(gland,mount.name,(x,-82.49,24.96));gland['sealed_wall_penetration']=wall
  for sign in (-1,1):
   pin=base.cylinder(name+('left' if sign<0 else 'right')+' captive lock',(x+sign*.54,-82.23,25.115),.075,.10,'metal','Z',FIX,vertices=20)
   attach(pin,body.name,(x+sign*.54,-82.23,25.095))
  data=bpy.data.lights.new(name+'task beam','SPOT');o=bpy.data.objects.new(data.name,data);bpy.data.collections[LIGHTS].objects.link(o)
  o.location=d['position'];o.rotation_euler=(Vector(d['target'])-o.location).to_track_quat('-Z','Y').to_euler()
  data.energy=d['energy_w'];data.color=d['color_linear'];data.spot_size=math.radians(d['cone_degrees']);data.spot_blend=d['blend'];data.shadow_soft_size=d['radius'];data.use_shadow=True
  o['fixture']=emitter.name;o['ship_fixed']=True;o['target']=json.dumps(d['target']);o['service_light_id']=fid;o['role']='service_bay_light'
 for o in bpy.data.collections[FIX].objects:o['revision']='fore-lighting-10';o['role']='hull'
 bpy.context.view_layer.update();assert f.protected()==before,'Prior objects/materials/lights/cameras changed'
 scene=bpy.context.scene;scene.name='KUHAI — Forward Shoulder Lighting 10';scene['revision']='fore-lighting-10';scene['fore10_config_sha256']=sha(a.config)
 a.output.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file;p=a.output.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(image.packed_file.data);image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 r={'revision':'fore-lighting-10','source_sha256':sha(a.output),'input_sha256':INPUT,'config_sha256':sha(a.config),'new_fixture_meshes':18,'new_lights':3,'prior_geometry_materials_lights_cameras_changed':False,'browser_tested':False,'published':False}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);build(p.parse_args())
