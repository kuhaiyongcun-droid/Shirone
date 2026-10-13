"""Fail-closed fore08 assembly checks plus unchanged bridge geometry/assembly.

Checks cover declared joints, host clearance and inspection panels; they are
not an engineering certification or exhaustive global ship collision proof.
"""
import argparse,json,sys,hashlib,collections
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
import assembly_check as assembly
import finish_study as f
import fore_study as fore
from surface_check import geometry
from surface_finish import sha

def visible():
 result={}
 def visit(c,hidden=False):
  hidden=hidden or c.hide_render
  if hidden or c.name=='SPACE':return
  for o in c.objects:
   if o.type=='MESH' and not o.hide_render:result[o.name]=o
  for child in c.children:visit(child,hidden)
 visit(bpy.context.scene.collection);return result

def require(scene,report):
 r=json.loads(Path(report).read_text())
 expected={'prior_content_preserved','closed_solids','equipment_and_routes_clear_of_hull',
 'all_functional_endpoints_in_fittings','mounts_and_tees_attached','inspection_panels_visible',
 'portable_images','repaired_geometry_unchanged','fore_closed_solids','fore_host_clearance',
 'fore_connections_attached','fore_inspection_panels_visible','declared_visibility_changes','existing_lighting_unchanged','fore_connector_axes_aligned','fore_corner_joints_closed'}
 assert r['source_sha256']==sha(scene),'Stale scene validation'
 assert r['passed'] and all(r['checks'].get(k) is True for k in expected),'Incomplete or failed validation'
 assert len(r['route_endpoints'])==24 and len(r['support_endpoints'])==48 and len(r['panel_visibility'])==18
 assert len(r['fore_routes'])==18 and len(r['fore_supports'])==20 and len(r['fore_visibility'])==4 and len(r['fore_attachments'])==23 and len(r['fore_connector_alignment'])==10 and len(r['fore_corner_joints'])==4,'Coverage changed; review it explicitly'
 return r

def light_records():
 return {o.name:{'matrix':[list(row) for row in o.matrix_world],
  'data':{k:(list(getattr(o.data,k)) if k=='color' else getattr(o.data,k,None)) for k in
          ('type','color','energy','angle','size','spot_size','spot_blend','shadow_soft_size','use_shadow')}}
  for o in bpy.data.objects if o.type=='LIGHT'}

def check(a):
 assert sha(a.baseline)==fore.INPUT
 before=geometry(a.baseline,'SIDE06_STRUCTURE','SIDE06 / ');basevisible=set(visible());lights_before=light_records()
 # Explicitly exempt ONLY cameras bearing the new revision prefix. All older
 # cameras, materials, lamps and object bytes remain in the protected contract.
 original=f.protected
 def protected():
  r=original();r['cameras']={k:v for k,v in r['cameras'].items() if not k.startswith(fore.P)};return r
 f.protected=protected
 a.prefix='SIDE06 / ';a.protected_prefix=fore.P;assembly.main(a)
 r=json.loads(a.output.read_text());after=geometry(a.scene,'SIDE06_STRUCTURE','SIDE06 / ')
 r['checks']['repaired_geometry_unchanged']=before==after
 r['checks']['existing_lighting_unchanged']=lights_before==light_records()
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();objects=visible()
 trees={};meshes={};verts=[];faces=[];owners=[];bad=[]
 for name,o in objects.items():
  t,vs,fs=assembly.tree(o,dg);trees[name]=t;meshes[name]=(vs,fs)
  off=len(verts);verts+=vs;faces.extend(tuple(off+i for i in face) for face in fs);owners.extend([name]*len(fs))
  if name.startswith(fore.P):
   e=o.evaluated_get(dg);m=e.to_mesh();bm=bmesh.new();bm.from_mesh(m)
   if not all(edge.is_manifold for edge in bm.edges) or bm.calc_volume(signed=True)<=0:bad.append(name)
   bm.free();e.to_mesh_clear()
 world=BVHTree.FromPolygons(verts,faces,all_triangles=True)
 hosts=[fore.P+n.removeprefix('FORM03 / ') for n in fore.HOSTS]+['FORM03 / Raised shoulder terminal','FORM03 / Forward root armor island']
 collisions=[];routes=[];supports=[];attachments=[];views=[];alignment=[]
 for name,o in objects.items():
  if not name.startswith(fore.P):continue
  if o.get('fore_kind') in ('equipment','route','handle'):
   for h in hosts:
    crossings=len(trees[name].overlap(trees[h]))
    contained=sum(assembly.inside(trees[h],p) for p in meshes[name][0][::max(1,len(meshes[name][0])//40)])
    if crossings or contained:collisions.append({'object':name,'host':h,'crossings':crossings,'contained_samples':contained})
  for prop,targetlist in [('fore_route_points',routes),('fore_support_points',supports)]:
   if prop in o:
    points=json.loads(o[prop])
    for side,p in [('start',points[0]),('end',points[-1])]:
     target=o['fore_'+side+'_target'];p=Vector(p)
     targetlist.append({'object':name,'end':side,'target':target,'attached':assembly.inside(trees[target],p)})
     if prop=='fore_route_points' and o.get('fore_kind')=='route':
      tangent=Vector(points[1])-Vector(points[0]) if side=='start' else Vector(points[-1])-Vector(points[-2])
      axis=objects[target].matrix_world.to_quaternion()@Vector((0,0,1))
      cosine=abs(tangent.normalized().dot(axis.normalized()))
      alignment.append({'route':name,'end':side,'fitting':target,'axis_cosine':cosine,'aligned':cosine>=.995})
  if 'fore_attachment_target' in o:
   target=o['fore_attachment_target'];p=Vector(json.loads(o['fore_attachment_point']))
   # Contact point must be inside BOTH attached members, not just near a target.
   attachments.append({'object':name,'target':target,'attached':assembly.inside(trees[target],p) and assembly.inside(trees[name],p)})
  if o.get('fore_inspection_panel'):
   vs=[o.matrix_world@Vector(p) for p in o.bound_box];lo=[min(v[k] for v in vs) for k in range(3)];hi=[max(v[k] for v in vs) for k in range(3)]
   pts=[Vector((lo[0]+(hi[0]-lo[0])*(.2+.6*x/10),lo[1]+(hi[1]-lo[1])*(.2+.6*y/10),hi[2]+.002)) for x in range(11) for y in range(11)]
   for camera in ('fore08_detail','fore08_reverse'):
    origin=bpy.data.objects[fore.P+camera].location;ok=0;hits=collections.Counter()
    for p in pts:
     d=p-origin;hit=world.ray_cast(origin,d.normalized(),d.length+.05);n=owners[hit[2]] if hit[2] is not None else 'none';hits[n]+=1
     if n==name or n in objects and objects[n].get('fore_group')==o.get('fore_group'):ok+=1
    views.append({'panel':name,'camera':camera,'visible_fraction':round(ok/len(pts),4),'occluders':dict(hits.most_common(5))})
 corners=[]
 for left,right,p in fore.CORNER_JOINTS:
  pt=Vector(p);ta=trees[fore.P+left];tb=trees[fore.P+right]
  corners.append({'members':[fore.P+left,fore.P+right],'point':p,
   'closed':assembly.inside(ta,pt) and assembly.inside(tb,pt)})
 current=set(objects);hidden=basevisible-current
 r['checks'].update(fore_closed_solids=not bad,fore_host_clearance=not collisions,
  fore_connections_attached=bool(routes and supports and attachments) and all(x['attached'] for x in routes+supports+attachments),
  fore_connector_axes_aligned=len(alignment)==10 and all(x['aligned'] for x in alignment),
  fore_corner_joints_closed=all(x['closed'] for x in corners),
  fore_inspection_panels_visible=len(views)==4 and all(x['visible_fraction']>=.90 for x in views),
  declared_visibility_changes=hidden==set(fore.REMOVED) and all(n.startswith(fore.P) for n in current-basevisible))
 r.update(fore_invalid_meshes=bad,fore_collisions=collisions,fore_routes=routes,fore_supports=supports,fore_attachments=attachments,fore_visibility=views,fore_connector_alignment=alignment,fore_corner_joints=corners,
  hidden_prior_objects=sorted(hidden),fore_visible_object_count=sum(n.startswith(fore.P) for n in current),
  baseline_sha256=sha(a.baseline),source_sha256=sha(a.scene),browser_tested=False,published=False)
 r['passed']=all(r['checks'].values());a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'checks':r['checks'],'bad':bad,'collisions':collisions,'bad_connections':[x for x in routes+supports+attachments if not x['attached']],
 'fore_visibility':views,'coverage':[len(routes),len(supports),len(attachments)]},indent=2),flush=True)
 assert r['passed'];require(a.scene,a.output)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--output',type=Path,required=True);check(p.parse_args())
