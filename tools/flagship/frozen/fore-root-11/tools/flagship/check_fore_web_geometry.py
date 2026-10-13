"""Source-vs-decoded-GLB ray depths detect lost boolean openings/occlusion.

No browser is involved. Test actual decoded mesh, not the Blender export scene.
"""
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fore_check import visible
from fore_surface_check import require
from surface_finish import sha

def world_tree(objects):
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();vs=[];fs=[]
 for o in objects:
  if o.type!='MESH':continue
  e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles();off=len(vs);vs.extend(o.matrix_world@v.co for v in m.vertices)
  fs.extend(tuple(off+i for i in t.vertices) for t in m.loop_triangles);e.to_mesh_clear()
 return BVHTree.FromPolygons(vs,fs,all_triangles=True)
def casts(tree,origin,points):
 out=[]
 for p in points:
  direction=Vector(p)-Vector(origin);hit=tree.ray_cast(Vector(origin),direction.normalized(),direction.length+10)
  out.append(list(hit[0]) if hit[0] is not None else None)
 return out
def main(a):
 require(a.source,a.validation);manifest=json.loads((a.assets/'model-manifest.json').read_text())
 assert sha(a.assets/'flagship.glb')==manifest['files']['flagship.glb']['sha256']
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));tree=world_tree(visible().values());samples=[]
 for camera in ('fore08_detail','fore08_reverse'):
  origin=list(bpy.data.objects['FORE08 / '+camera].location)
  for unit,x in ((1,-205.8),(2,-195.4)):
   points=[(x-1.56+3.12*i/10,-79.1+1.8*j/10,24.142) for i in range(11) for j in range(11)]
   samples.append({'view':camera,'target':'U'+str(unit)+' lid','origin':origin,'points':points,'source_hits':casts(tree,origin,points)})
  points=[(-201.75+i*.55,-80.8+j*.7,19.502) for i in range(5) for j in range(7)]
  samples.append({'view':camera,'target':'channel floor','origin':origin,'points':points,'source_hits':casts(tree,origin,points)})
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str((a.assets/'flagship.glb').resolve()))
 for o in bpy.context.scene.objects:
  if o.parent is None:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 tree=world_tree(list(bpy.context.scene.objects));rows=[]
 for group in samples:
  errors=[]
  for before,after in zip(group['source_hits'],casts(tree,group['origin'],group['points'])):
   errors.append((Vector(before)-Vector(after)).length if before is not None and after is not None else None)
  close=sum(e is not None and e<=.1 for e in errors);fraction=close/len(errors)
  rows.append({'view':group['view'],'target':group['target'],'rays':len(errors),'within_0_1_source_meter':close,'fraction':fraction,'max_distance_source_m':max(e for e in errors if e is not None),'passed':fraction>=.95})
 r={'source_sha256':sha(a.source),'glb_sha256':sha(a.assets/'flagship.glb'),'rows':rows,'total_rays':sum(x['rays'] for x in rows),'passed':len(rows)==6 and all(x['passed'] for x in rows),'scope':'Two existing cameras; two lid grids plus recessed floor. Detects export closure or new foreground occlusion; not exhaustive hull collision or browser test.','browser_tested':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2),flush=True);assert r['passed'],'Exported recess differs from verified editable source'
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
