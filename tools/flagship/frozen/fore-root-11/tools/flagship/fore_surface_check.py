"""Freeze exact evaluated geometry AND fore08 assembly metadata for fore09.

The 16 passing fore08 checks are carried forward only after equality of every
evaluated mesh, matrix, split normal, declared joint, visibility and camera is
proven. This does not substitute an untested geometry revision for its input.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f
import fore_surface as s
from fore_check import require as fore_require,visible,light_records
from surface_check import geometry as bridge_geometry
from surface_finish import sha

REQUIRED={'immutable_fore08_validated','all_previous_content_preserved','fore_evaluated_geometry_and_connections_unchanged',
 'bridge_evaluated_geometry_unchanged','lighting_unchanged','only_declared_visibility_changed','images_portable'}
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
def fore_geometry(collection,prefix):
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();rows={}
 for o in sorted(bpy.data.collections[collection].objects,key=lambda x:x.name):
  e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
  meta={k:(o[k].replace(prefix,'LOCAL / ') if isinstance(o[k],str) else o[k]) for k in o.keys() if k.startswith('fore_')}
  row={'matrix':[list(v) for v in o.matrix_world],'vertices':[list(v.co) for v in m.vertices],
   'triangles':[list(t.vertices) for t in m.loop_triangles],'normals':[list(v.vector) for v in m.corner_normals],
   'assembly':meta,'role':o.get('role'),'object_hide_render':o.hide_render}
  rows[o.name.removeprefix(prefix)]=digest(row);e.to_mesh_clear()
 return rows
def require(scene,report):
 r=json.loads(Path(report).read_text());assert r['source_sha256']==sha(scene),'Stale fore09 validation'
 assert r['baseline_sha256']==s.INPUT and r['passed'] and all(r['checks'].get(k) is True for k in REQUIRED)
 assert r['fore_object_count']==100 and r['bridge_object_count']==342
 assert r['input_assembly_checks_count']==16 and all(r['input_assembly_checks'].values())
 return r
def check(a):
 assert sha(a.baseline)==s.INPUT;old=fore_require(a.baseline,a.input_validation)
 bg_before=bridge_geometry(a.baseline,'SIDE06_STRUCTURE','SIDE06 / ')
 f.PREFIX=s.P;protected_before=f.protected();fg_before=fore_geometry(s.OLD,s.OLDP)
 names_before=set(visible());lights_before=light_records()
 bg_after=bridge_geometry(a.scene,'SIDE06_STRUCTURE','SIDE06 / ')
 protected_after=f.protected();fg_after=fore_geometry(s.NEW,s.P)
 names_after=set(visible());normalized={s.OLDP+n.removeprefix(s.P) if n.startswith(s.P) else n for n in names_after}
 images=[{'name':i.name,'packed':bool(i.packed_file),'relative':i.filepath.startswith('//')} for i in bpy.data.images if i.type=='IMAGE' and i.users]
 checks={'immutable_fore08_validated':True,'all_previous_content_preserved':protected_before==protected_after,
  'fore_evaluated_geometry_and_connections_unchanged':fg_before==fg_after,'bridge_evaluated_geometry_unchanged':bg_before==bg_after,
  'lighting_unchanged':lights_before==light_records(),'only_declared_visibility_changed':normalized==names_before and not any(n.startswith(s.OLDP) for n in names_after),
  'images_portable':all(i['packed'] and i['relative'] for i in images)}
 r={'revision':'fore-surface-09','source_sha256':sha(a.scene),'baseline_sha256':sha(a.baseline),
  'input_validation_sha256':sha(a.input_validation),'input_assembly_checks':old['checks'],'input_assembly_checks_count':len(old['checks']),
  'input_proof':'Exact equality of evaluated geometry, split normals, world matrices, all fore_* assembly declarations, visible objects and existing cameras. Material-only changes cannot move a joint or occlude a panel.',
  'checks':checks,'passed':all(checks.values()),'fore_object_count':len(fg_after),'bridge_object_count':len(bg_after),
  'fore_geometry_sha256':digest(fg_after),'bridge_geometry_sha256':digest(bg_after),'fore_object_digests':fg_after,
  'images':images,'browser_tested':False,'published':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(checks),flush=True);require(a.scene,a.output)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--input-validation',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--output',type=Path,required=True);check(p.parse_args())
