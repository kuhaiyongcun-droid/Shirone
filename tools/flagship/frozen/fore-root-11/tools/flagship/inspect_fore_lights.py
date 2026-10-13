"""Decode exact light-only GLB; check six sources including preserved bridge07."""
import argparse,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from surface_finish import sha
from fore_lighting import DEFAULT
from export_fore_lighting import light_definitions
def main(a):
 cfg=json.loads(a.config.read_text());profile=json.loads((a.assets/'service-lighting.json').read_text());assert profile['config_sha256']==sha(a.config) and profile['lights_sha256']==sha(a.assets/'service-lights.glb')
 assert profile['model_sha256']==sha(a.assets/'flagship.glb')
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str((a.assets/'service-lights.glb').resolve()),export_import_convert_lighting_mode='SPEC');obs=list(bpy.context.scene.objects)
 for o in obs:
  if o.parent not in obs:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 bpy.context.view_layer.update();rows=[]
 for d in light_definitions(cfg):
  o=bpy.data.objects['WEB10 / '+d['group']+' / '+d['id']];axis=o.matrix_world.to_quaternion()@Vector((0,0,-1));target=(Vector(d['target'])-Vector(d['position'])).normalized()
  r={'id':d['id'],'position_error_m':(o.matrix_world.translation-Vector(d['position'])).length,'direction_dot':axis.dot(target),'energy_error_w':abs(o.data.energy*10000-d['energy_w']),
   'cone_error':abs(o.data.spot_size-math.radians(d['cone_degrees'])),'blend_error':abs(o.data.spot_blend-d['blend']),'color_error':max(abs(x-y) for x,y in zip(o.data.color,d['color_linear']))}
  r['passed']=r['position_error_m']<.0001 and r['direction_dot']>.999999 and r['energy_error_w']<.002 and r['cone_error']<.00001 and r['blend_error']<.00001 and r['color_error']<.00001 and o.get('service_group')==d['group'];rows.append(r)
 r={'lights_sha256':sha(a.assets/'service-lights.glb'),'model_sha256':sha(a.assets/'flagship.glb'),'config_sha256':sha(a.config),'lights':rows,'count':len(rows),'passed':len(rows)==6 and all(x['passed'] for x in rows),'finite_radius_preserved':False,'browser_tested':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));assert r['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
