"""Repeat assembly inspection and prove only declared lights were added."""
import argparse,json,math,sys,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import assembly_check as assembly
from surface_check import geometry
from surface_finish import sha
from lighting_study import DEFAULT
def check(a):
 cfg=json.loads(a.config.read_text());assert sha(a.baseline)==cfg['source_sha256']
 before=geometry(a.baseline,'SIDE06_STRUCTURE','SIDE06 / ');names={o.name for o in bpy.data.objects}
 after=geometry(a.scene,'SIDE06_STRUCTURE','SIDE06 / ');additions={o.name for o in bpy.data.objects}-names
 expected={cfg['prefix']+x['name'] for x in cfg['lights']};assert additions==expected
 lights=[]
 for d in cfg['lights']:
  o=bpy.data.objects[cfg['prefix']+d['name']];assert o.type=='LIGHT' and o.data.type=='SPOT'
  axis=o.matrix_world.to_quaternion()@Vector((0,0,-1));direction=(Vector(d['target'])-o.location).normalized()
  valid=(o.location-Vector(d['position'])).length<.0001 and abs(o.data.energy-d['energy_w'])<.001 and axis.dot(direction)>.999999
  valid=valid and max(abs(x-y) for x,y in zip(o.data.color,d['color_linear']))<.00001 and abs(o.data.spot_size-math.radians(d['cone_degrees']))<.00001
  valid=valid and abs(o.data.spot_blend-d['blend'])<.00001 and abs(o.data.shadow_soft_size-d['radius'])<.00001 and o.data.use_shadow==d['cast_shadow']
  gap=None
  if d['fixture']:
   gap=(o.location-bpy.data.objects[d['fixture']].matrix_world.translation).length;valid=valid and gap<d['max_fixture_distance']
  lights.append({'name':o.name,'matches_config':valid,'distance_from_existing_emitter':gap,'ship_fixed':o.get('ship_fixed') is True})
 a.prefix='SIDE06 / ';a.protected_prefix=cfg['prefix'];assembly.main(a)
 r=json.loads(a.output.read_text());r['checks'].update(repaired_geometry_unchanged=before==after,
   declared_lights_only=additions==expected,lighting_configuration=all(x['matches_config'] and x['ship_fixed'] for x in lights))
 r.update(passed=all(r['checks'].values()),baseline_sha256=sha(a.baseline),config_sha256=sha(a.config),
   geometry_sha256=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest(),geometry_object_count=len(after),lights=lights)
 a.output.write_text(json.dumps(r,indent=2)+'\n');print('LIGHT_CHECK',json.dumps(r['checks']),flush=True);assert r['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);check(p.parse_args())
