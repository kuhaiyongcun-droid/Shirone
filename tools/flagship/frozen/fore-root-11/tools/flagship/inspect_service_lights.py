"""Decode the light-only GLB and compare placement, aim, cone, color and power."""
import argparse,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from surface_finish import sha
from lighting_study import DEFAULT
def inspect(a):
 cfg=json.loads(a.config.read_text());profile=json.loads((a.assets/'service-lighting.json').read_text())
 assert profile['config_sha256']==sha(a.config) and profile['lights_sha256']==sha(a.assets/'service-lights.glb')
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str((a.assets/'service-lights.glb').resolve()),export_import_convert_lighting_mode='SPEC')
 imported=list(bpy.context.scene.objects)
 for o in imported:
  if o.parent not in imported:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 bpy.context.view_layer.update();rows=[]
 for d in cfg['lights']:
  o=bpy.data.objects['WEB07 / '+d['name']];assert o.type=='LIGHT';world=o.matrix_world
  target=(Vector(d['target'])-Vector(d['position'])).normalized();actual=world.to_quaternion()@Vector((0,0,-1))
  row={'light':o.name,'position_error_m':(world.translation-Vector(d['position'])).length,
   'direction_dot':actual.dot(target),'energy_error_w':abs(o.data.energy*10000-d['energy_w']),
   'cone_error_radians':abs(o.data.spot_size-math.radians(d['cone_degrees'])),
   'blend_error':abs(o.data.spot_blend-d['blend']),
   'color_error':max(abs(x-y) for x,y in zip(o.data.color,d['color_linear']))}
  row['passed']=row['position_error_m']<.0001 and row['direction_dot']>.999999 and row['energy_error_w']<.002 and row['cone_error_radians']<.00001 and row['blend_error']<.00001 and row['color_error']<.00001
  rows.append(row)
 r={'passed':all(x['passed'] for x in rows),'checks':rows,'decoded_light_count':sum(o.type=='LIGHT' for o in imported),
    'geometry_unchanged':sha(a.assets/'flagship.glb')==profile['model_sha256'],'browser_tested':False,
    'note':'Punctual GLB does not encode original finite-source radius; offline comparison exposes this limitation.'}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));assert r['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);inspect(p.parse_args())
