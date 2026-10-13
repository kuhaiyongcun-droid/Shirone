"""Freeze prior content; validate mounted lamps, beam aims and panel visibility."""
import argparse,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f
import assembly_check as ac
import fore_lighting as s
from fore_surface_check import fore_geometry,require as input_require
from surface_check import geometry as bridge_geometry
from fore_check import visible,light_records
from check_fore_web_geometry import world_tree,casts
from surface_finish import sha
REQUIRED={'input_validated','prior_content_preserved','fore_geometry_connections_unchanged','bridge_geometry_unchanged','prior_lights_unchanged','declared_additions_only','fixture_solids_closed','fixture_contacts_attached','fixtures_clear_of_equipment','beams_match_config','beam_paths_clear','inspection_depths_preserved','portable_images'}
def require(scene,report):
 r=json.loads(Path(report).read_text());assert r['source_sha256']==sha(scene) and r['baseline_sha256']==s.INPUT
 assert r['passed'] and all(r['checks'].get(k) is True for k in REQUIRED),'Incomplete fore10 check'
 assert r['fore_objects']==100 and r['bridge_objects']==342 and len(r['fixture_contacts'])==18 and len(r['lights'])==3 and len(r['inspection_views'])==4
 return r
def check(a):
 assert sha(a.baseline)==s.INPUT;input_require(a.baseline,a.input_validation);cfg=json.loads(a.config.read_text());assert cfg['source_sha256']==s.INPUT
 bgb=bridge_geometry(a.baseline,'SIDE06_STRUCTURE','SIDE06 / ');fgb=fore_geometry('FORE09_STRUCTURE','FORE09 / ');f.PREFIX=s.P;pb=f.protected();lightsb=light_records();namesb={o.name for o in bpy.data.objects};visb=set(visible())
 tree=world_tree(visible().values());samples=[]
 for camera in ('fore08_detail','fore08_reverse'):
  origin=list(bpy.data.objects['FORE08 / '+camera].location)
  for x in (-205.8,-195.4):
   pts=[(x-1.56+3.12*i/10,-79.1+1.8*j/10,24.142) for i in range(11) for j in range(11)]
   samples.append((camera,x,origin,pts,casts(tree,origin,pts)))
 bga=bridge_geometry(a.scene,'SIDE06_STRUCTURE','SIDE06 / ');fga=fore_geometry('FORE09_STRUCTURE','FORE09 / ');pa=f.protected();dg=bpy.context.evaluated_depsgraph_get();obs=visible()
 trees={n:ac.tree(o,dg)[0] for n,o in obs.items()};contacts=[];bad=[];collisions=[]
 equipment=[n for n,o in obs.items() if n.startswith('FORE09 / ') and o.get('fore_kind') in ('equipment','route','handle','mount')]
 for o in bpy.data.collections[s.FIX].objects:
  e=o.evaluated_get(dg);mesh=e.to_mesh();bm=bmesh.new();bm.from_mesh(mesh)
  if not all(x.is_manifold for x in bm.edges) or bm.calc_volume(signed=True)<=0:bad.append(o.name)
  bm.free();e.to_mesh_clear();target=o['fixture_attachment_target'];point=Vector(json.loads(o['fixture_attachment_point']))
  contacts.append({'object':o.name,'target':target,'attached':ac.inside(trees[o.name],point) and ac.inside(trees[target],point)})
  for n in equipment:
   if trees[o.name].overlap(trees[n]):collisions.append([o.name,n])
 tree=world_tree(obs.values());views=[]
 for camera,x,origin,pts,old in samples:
  new=casts(tree,origin,pts);errors=[(Vector(a)-Vector(b)).length if a is not None and b is not None else None for a,b in zip(old,new)]
  views.append({'camera':camera,'unit_x':x,'samples':len(errors),'unchanged':all(e is not None and e<.0001 for e in errors)})
 rows=[]
 for d in cfg['fixtures']:
  o=bpy.data.objects[s.P+d['id']+' / task beam'];direction=(Vector(d['target'])-o.location).normalized();axis=o.matrix_world.to_quaternion()@Vector((0,0,-1))
  valid=(o.location-Vector(d['position'])).length<.0001 and axis.dot(direction)>.999999 and abs(o.data.energy-d['energy_w'])<.001
  valid=valid and o.data.type=='SPOT' and abs(o.data.spot_size-math.radians(d['cone_degrees']))<.00001 and abs(o.data.spot_blend-d['blend'])<.00001 and abs(o.data.shadow_soft_size-d['radius'])<.00001
  valid=valid and max(abs(x-y) for x,y in zip(o.data.color,d['color_linear']))<.00001 and o.data.use_shadow
  start=o.location;distance=(Vector(d['target'])-start).length;hit=tree.ray_cast(start,direction,distance)
  fixture=bpy.data.objects[o['fixture']];gap=(start-fixture.location).length
  receiver=None
  if hit[0] is not None:
   hits=[]
   for name,t in trees.items():
    h=t.ray_cast(start,direction,distance)
    if h[0] is not None:hits.append((h[3],name))
   receiver=min(hits)[1] if hits else None
  # A lamp aimed at a visible casing/union is expected to hit that receiver.
  # Floor-directed lamps must remain unobstructed to their in-air target.
  path_clear=receiver.startswith(d['receiver_prefix']) if receiver and d.get('receiver_prefix') else hit[0] is None
  rows.append({'id':d['id'],'matches_config':valid,'ship_fixed':o.get('ship_fixed') is True,'lens_distance':gap,'within_fixture':gap<.15,'clear_to_target':path_clear,'first_receiver':receiver,'declared_receiver_prefix':d.get('receiver_prefix'),'first_block_distance':hit[3]})
 additions={o.name for o in bpy.data.objects}-namesb;expected={o.name for c in (s.FIX,s.LIGHTS) for o in bpy.data.collections[c].objects}
 images=[i for i in bpy.data.images if i.type=='IMAGE' and i.users]
 checks={'input_validated':True,'prior_content_preserved':pb==pa,'fore_geometry_connections_unchanged':fgb==fga,'bridge_geometry_unchanged':bgb==bga,
 'prior_lights_unchanged':lightsb=={k:v for k,v in light_records().items() if k in lightsb},'declared_additions_only':additions==expected and len(additions)==21 and set(obs)-set(o.name for o in bpy.data.collections[s.FIX].objects)==visb,
 'fixture_solids_closed':not bad,'fixture_contacts_attached':all(r['attached'] for r in contacts),'fixtures_clear_of_equipment':not collisions,
 'beams_match_config':all(r['matches_config'] and r['ship_fixed'] and r['within_fixture'] for r in rows),'beam_paths_clear':all(r['clear_to_target'] for r in rows),
 'inspection_depths_preserved':all(r['unchanged'] for r in views),'portable_images':all(i.packed_file and i.filepath.startswith('//') for i in images)}
 r={'revision':'fore-lighting-10','source_sha256':sha(a.scene),'baseline_sha256':s.INPUT,'input_validation_sha256':sha(a.input_validation),'config_sha256':sha(a.config),'checks':checks,'passed':all(checks.values()),'fore_objects':len(fga),'bridge_objects':len(bga),'fixture_contacts':contacts,'fixture_bad_meshes':bad,'fixture_collisions':collisions,'lights':rows,'inspection_views':views,'browser_tested':False,'published':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2),flush=True);require(a.scene,a.output)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--input-validation',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--config',type=Path,default=s.DEFAULT);p.add_argument('--output',type=Path,required=True);check(p.parse_args())
