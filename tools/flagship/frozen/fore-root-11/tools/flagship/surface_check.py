"""Geometry freeze plus the real assembly checks, bound to exact scene bytes."""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import assembly_check as assembly
from surface_finish import sha,INPUT

def geometry(path,collection,prefix):
 bpy.ops.wm.open_mainfile(filepath=str(path.resolve()));bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();rows={}
 for o in sorted(bpy.data.collections[collection].objects,key=lambda o:o.name):
  e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
  data={'matrix':[list(row) for row in o.matrix_world],'vertices':[list(v.co) for v in m.vertices],
        'triangles':[list(t.vertices) for t in m.loop_triangles],'normals':[list(n.vector) for n in m.corner_normals],
        'assembly':{k:(o[k].replace(prefix,'LOCAL / ') if isinstance(o[k],str) else o[k]) for k in
                    ('assembly_route','route_points','route_radius','start_target','end_target','support_points','mate_manifold','assembly_group') if k in o}}
  rows[o.name.removeprefix(prefix)]=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest();e.to_mesh_clear()
 return rows
def main(a):
 assert sha(a.baseline)==INPUT
 before=geometry(a.baseline,'SIDE05_STRUCTURE','SIDE05 / ');after=geometry(a.scene,'SIDE06_STRUCTURE','SIDE06 / ')
 a.prefix='SIDE06 / ';assembly.main(a)
 r=json.loads(a.output.read_text());r['checks']['repaired_geometry_unchanged']=before==after
 r['geometry_sha256']=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest()
 r['geometry_object_count']=len(after);r['baseline_sha256']=sha(a.baseline);r['passed']=all(r['checks'].values())
 a.output.write_text(json.dumps(r,indent=2)+'\n');assert r['passed'],r['checks']
 print('SURFACE_CHECK',json.dumps(r['checks']),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
