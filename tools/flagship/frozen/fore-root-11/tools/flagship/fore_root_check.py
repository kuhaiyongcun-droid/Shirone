"""Bound fore11 assembly, visibility and baseline preservation checks."""
import argparse,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_root as s
import assembly_check as ac
from fore_light_check import require as input_require
from fore_surface_check import fore_geometry,digest
from fore_check import visible,light_records
from check_fore_web_geometry import world_tree,casts
from surface_finish import sha
REQUIRED={'validated_fore10_input','prior_content_preserved','fore09_geometry_connections_preserved','bridge_geometry_preserved','fore10_fixture_geometry_metadata_preserved','lighting_preserved','declared_visibility_only','new_solids_closed','all_declared_contacts_attached','all_parts_anchored_to_hull','functional_parts_clear_of_prior_geometry','link_clear_of_clevis_cheeks','pin_axes_aligned','old_inspection_depths_preserved','new_link_and_floor_visible','seams_open_to_common_seats','turret_seat_depth_preserved','portable_images'}
def require(scene,report):
 r=json.loads(Path(report).read_text());assert r['source_sha256']==sha(scene) and r['baseline_sha256']==s.INPUT
 assert r['passed'] and all(r['checks'].get(k) is True for k in REQUIRED),'Incomplete fore11 validation'
 assert r['new_meshes']==38 and len(r['contacts'])==47 and r['preserved_counts']==[100,342,18]
 assert len(r['old_views'])==22 and len(r['new_views'])==4 and len(r['seams'])==4 and len(r['pin_axes'])==2
 return r
def frozen():
 return {c:fore_geometry(c,p) for c,p in [('FORE09_STRUCTURE','FORE09 / '),('SIDE06_STRUCTURE','SIDE06 / '),('FORE10_FIXTURES','FORE10 / ')]}
def fixture_meta():return {o.name:{k:str(o[k]) for k in o.keys()} for c in ('FORE10_FIXTURES','FORE10_LIGHTS') for o in bpy.data.collections[c].objects}
def old_samples():
 rows=[]
 for camera in ('fore08_detail','fore08_reverse'):
  origin=list(bpy.data.objects['FORE08 / '+camera].location)
  for i,x in enumerate((-205.8,-195.4)):
   pts=[(x-1.56+3.12*a/10,-79.1+1.8*b/10,24.142) for a in range(11) for b in range(11)];rows.append({'camera':camera,'panel':'fore U'+str(i+1),'origin':origin,'points':pts})
 for label in ('Inset module face','Canister instrument saddle'):
  for i in range(3):
   o=bpy.data.objects['SIDE06 / '+label+('' if i==0 else '.'+str(i).zfill(3))];vs=[Vector(v) for v in o.bound_box];lo=Vector(tuple(min(v[k] for v in vs) for k in range(3)));hi=Vector(tuple(max(v[k] for v in vs) for k in range(3)))
   pts=[list(o.matrix_world@Vector((lo.x+(hi.x-lo.x)*(.1+.8*a/10),lo.y-.002,lo.z+(hi.z-lo.z)*(.1+.8*b/10)))) for a in range(11) for b in range(11)]
   for camera in ('side03_detail','side03_reverse','side05_front'):rows.append({'camera':camera,'panel':o.name,'origin':list(bpy.data.objects[camera].location),'points':pts})
 return rows
def depths_equal(before,after,tolerance=.0001):return all(a is not None and b is not None and (Vector(a)-Vector(b)).length<tolerance for a,b in zip(before,after))
def check(a):
 input_require(a.baseline,a.input_validation);assert sha(a.baseline)==s.INPUT
 cfg=json.loads(a.config.read_text());assert cfg['input_sha256']==s.INPUT;s.CFG=cfg;s.ANGLE=math.radians(cfg['opening_angle_degrees']);removed=set([cfg['removed_object']]+cfg['removed_overlays'])
 bpy.ops.wm.open_mainfile(filepath=str(a.baseline.resolve()));before=s.protected();frozen_before=frozen();meta_before=fixture_meta();light_before=light_records();vis_before=set(visible());names_before=set(bpy.data.objects.keys())
 oldtree=world_tree(visible().values());samples=old_samples()
 for row in samples:row['hits']=casts(oldtree,row['origin'],row['points'])
 oldarmor=ac.tree(bpy.data.objects[cfg['removed_object']],bpy.context.evaluated_depsgraph_get())[0]
 seatpoints=[Vector((-211+3.8*math.cos(t*2*math.pi/32),-56+3.8*math.sin(t*2*math.pi/32),26)) for t in range(32)]
 oldseats=[oldarmor.ray_cast(p,Vector((0,0,-1)),8)[0] for p in seatpoints]
 del oldtree
 bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()));assert bpy.context.scene['root11_config_sha256']==sha(a.config);bpy.context.view_layer.update();after=s.protected();frozen_after=frozen();obs=visible();new=list(bpy.data.collections[s.NEW].objects);dg=bpy.context.evaluated_depsgraph_get();trees={};mesh={};bad=[];contacts=[]
 def tree(name):
  if name not in trees:trees[name],vs,fs=ac.tree(obs[name],dg);mesh[name]=(vs,fs)
  return trees[name]
 for o in new:
  tree(o.name);e=o.evaluated_get(dg);m=e.to_mesh();bm=bmesh.new();bm.from_mesh(m)
  if not all(x.is_manifold for x in bm.edges) or bm.calc_volume(signed=True)<=0:bad.append(o.name)
  bm.free();e.to_mesh_clear()
  for row in json.loads(o.get('root_contacts','[]')):
   p=Vector(row['point']);ok=row['target'] in obs and ac.inside(tree(o.name),p) and ac.inside(tree(row['target']),p)
   contacts.append({'object':o.name,**row,'attached':ok})
 graph={o.name:set() for o in new};graph[cfg['body']]=set()
 for row in contacts:
  if row['attached']:graph.setdefault(row['object'],set()).add(row['target']);graph.setdefault(row['target'],set()).add(row['object'])
 reached={cfg['body']};pending=list(reached)
 while pending:
  for n in graph[pending.pop()]-reached:reached.add(n);pending.append(n)
 boxes={n:([min((o.matrix_world@Vector(v))[k] for v in o.bound_box) for k in range(3)],[max((o.matrix_world@Vector(v))[k] for v in o.bound_box) for k in range(3)]) for n,o in obs.items()}
 def may_overlap(x,y):
  lo,hi=boxes[x];a0,a1=boxes[y];return all(lo[k]<a1[k] and hi[k]>a0[k] for k in range(3))
 collisions=[]
 for o in new:
  if o.get('root_kind') not in ('clevis','pin','load_link','fastener'):continue
  for name in vis_before-removed:
   if not may_overlap(o.name,name):continue
   cross=tree(o.name).overlap(tree(name));vs=mesh[o.name][0]
   inside=any(ac.inside(tree(name),v) for v in vs[::max(1,len(vs)//30)])
   if cross or inside:collisions.append({'object':o.name,'prior_object':name,'crossings':len(cross),'contained_sample':inside})
 link=s.P+'Captured longitudinal shear link';cheeks=[o.name for o in new if o.get('root_kind')=='clevis'];clearance=[]
 for name in cheeks:clearance.append({'link':link,'cheek':name,'crossings':len(tree(link).overlap(tree(name))),'contained':any(ac.inside(tree(name),v) for v in mesh[link][0])})
 axes=[];direction=(s.point(0,1,0)-s.point(0,0,0)).normalized()
 for o in new:
  if o.get('root_kind')=='pin':
   cosine=abs((o.matrix_world.to_quaternion()@Vector((0,0,1))).dot(direction));axes.append({'pin':o.name,'cosine':cosine,'aligned':cosine>.999999})
 world=world_tree(obs.values());old_views=[]
 for row in samples:old_views.append({'camera':row['camera'],'panel':row['panel'],'rays':len(row['points']),'unchanged':depths_equal(row['hits'],casts(world,row['origin'],row['points']))})
 new_views=[]
 for camera in cfg['cameras']:
  cam=bpy.data.objects[s.P+camera];origin=cam.location
  for label,pts,target in [('load link',[s.point(-4.4+8.8*i/16,-.25+.5*j/4,23.863) for i in range(17) for j in range(5)],link),('inspection pan',[s.point(u,v,22.203) for u in (-3.5,-1.75,0,1.75,3.5) for v in (-2.2,2.2)],s.P+'Root inspection pan')]:
   clear=0;in_frame=0
   for p in pts:
    delta=p-origin;actual=world.ray_cast(origin,delta.normalized(),delta.length+.1)[0];expected=tree(target).ray_cast(origin,delta.normalized(),delta.length+.1)[0]
    q=world_to_camera_view(bpy.context.scene,cam,p);in_frame+=int(q.z>0 and .02<q.x<.98 and .02<q.y<.98)
    clear+=int(actual is not None and expected is not None and (actual-expected).length<.005)
   new_views.append({'camera':camera,'surface':label,'rays':len(pts),'visible':clear,'visible_fraction':clear/len(pts),'in_frame':in_frame,'passed':clear/len(pts)>=.9 and in_frame==len(pts)})
 seams=[]
 for i,x in enumerate(cfg['seams_x']):
  for j,y in enumerate((-41,-53)):
   p=Vector((x,y,26));hit=world.ray_cast(p,Vector((0,0,-1)),8)[0];expected=tree(s.P+f'Joint {i+1} common seat {j+1}').ray_cast(p,Vector((0,0,-1)),8)[0]
   seams.append({'xy':[x,y],'open_to_seat':hit is not None and expected is not None and (hit-expected).length<.005,'z':hit.z if hit else None})
 newarmor=tree(s.P+'Forward armor segment');newseats=[newarmor.ray_cast(p,Vector((0,0,-1)),8)[0] for p in seatpoints]
 seat_ok=depths_equal(oldseats,newseats)
 newnames={o.name for o in new};actual_added=set(bpy.data.objects.keys())-names_before;expected_added=newnames|{o.name for o in bpy.data.collections[s.CUT].objects}|{s.P+k for k in cfg['cameras']}
 images=[i for i in bpy.data.images if i.type=='IMAGE' and i.users]
 checks={'validated_fore10_input':True,'prior_content_preserved':before==after,'fore09_geometry_connections_preserved':frozen_before['FORE09_STRUCTURE']==frozen_after['FORE09_STRUCTURE'],
  'bridge_geometry_preserved':frozen_before['SIDE06_STRUCTURE']==frozen_after['SIDE06_STRUCTURE'],'fore10_fixture_geometry_metadata_preserved':frozen_before['FORE10_FIXTURES']==frozen_after['FORE10_FIXTURES'] and meta_before==fixture_meta(),
  'lighting_preserved':light_before==light_records(),'declared_visibility_only':set(obs)==(vis_before-removed)|newnames and actual_added==expected_added,
  'new_solids_closed':not bad,'all_declared_contacts_attached':len(contacts)==47 and all(r['attached'] for r in contacts),'all_parts_anchored_to_hull':newnames<=reached,
  'functional_parts_clear_of_prior_geometry':not collisions,'link_clear_of_clevis_cheeks':all(not r['crossings'] and not r['contained'] for r in clearance),'pin_axes_aligned':len(axes)==2 and all(r['aligned'] for r in axes),
  'old_inspection_depths_preserved':all(r['unchanged'] for r in old_views),'new_link_and_floor_visible':all(r['passed'] for r in new_views),'seams_open_to_common_seats':all(r['open_to_seat'] for r in seams),'turret_seat_depth_preserved':seat_ok,'portable_images':all(i.packed_file and i.filepath.startswith('//') for i in images)}
 r={'revision':'fore-root-11','source_sha256':sha(a.scene),'baseline_sha256':s.INPUT,'input_validation_sha256':sha(a.input_validation),'config_sha256':sha(a.config),'checks':checks,'passed':all(checks.values()),'new_meshes':len(new),'preserved_counts':[len(frozen_after[x]) for x in ('FORE09_STRUCTURE','SIDE06_STRUCTURE','FORE10_FIXTURES')],
  'contacts':contacts,'unanchored_parts':sorted(newnames-reached),'bad_solids':bad,'collisions':collisions,'link_clearance':clearance,'pin_axes':axes,'old_views':old_views,'new_views':new_views,'seams':seams,'turret_seat_rays':len(seatpoints),'browser_tested':False,'published':False,
  'scope':'Declared attachment points, clevis/link clearance, existing equipment views and two new cameras. Not a global engineering, stress or all-angle collision certification.'}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'checks':checks,'bad_solids':bad,'bad_contacts':[x for x in contacts if not x['attached']],'collisions':collisions,'new_views':new_views,'unanchored':r['unanchored_parts']},indent=2),flush=True);require(a.scene,a.output)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--input-validation',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--config',type=Path,default=s.DEFAULT);p.add_argument('--output',type=Path,required=True);check(p.parse_args())
