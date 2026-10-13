"""Bake the new material sample; preserve both source geometry and old bakes."""
import argparse,json,sys,math
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_surface as s
import surface_bake as bake
from surface_finish import sha
from fore_surface_check import require

def main(a):
 validation=require(a.source,a.validation);assert not a.output.exists();a.output.mkdir(parents=True);texdir=a.output/'textures';texdir.mkdir()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.context.scene
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.render.threads_mode='FIXED';scene.render.threads=6
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();objs=list(bpy.data.collections[s.NEW].objects)
 equipment=[o for o in objs if o.get('fore_kind')!='host'];hosts=[o for o in objs if o.get('fore_kind')=='host'];assert len(equipment)==98 and len(hosts)==2
 col=bpy.data.collections.new('FORE09_BAKED');scene.collection.children.link(col)
 source_vertices=[];source_normals=[];source_faces=[]
 for o in equipment:
  e=o.evaluated_get(dg);m=e.to_mesh();off=len(source_vertices);normal_matrix=o.matrix_world.to_3x3().inverted().transposed()
  source_vertices.extend(tuple(o.matrix_world@v.co) for v in m.vertices)
  for p in m.polygons:
   source_faces.append(tuple(off+i for i in p.vertices));source_normals.extend(tuple((normal_matrix@m.corner_normals[i].vector).normalized()) for i in p.loop_indices)
  e.to_mesh_clear()
 obj=bake.evaluated_group(equipment,'fore09-service',dg,col);obj.name='BAKED09 / Service surfaces';obj.data.name=obj.name
 assert source_vertices==[tuple(v.co) for v in obj.data.vertices] and source_faces==[tuple(p.vertices) for p in obj.data.polygons]
 max_normal_error=max(max(abs(a-b) for a,b in zip(n,v.vector)) for n,v in zip(source_normals,obj.data.corner_normals))
 # Blender re-encodes custom loop normals in a different local tangent basis
 # when merging objects. Compare normalized directions, not arbitrary component
 # equality. Source fore08/fore09 normals still have the separate EXACT freeze.
 # Require <0.05 degree, below the subsequent 10-bit GLB normal quantization.
 def angular_error(a,b):
  dot=sum(float(x)*float(y) for x,y in zip(a,b));na=sum(float(x)**2 for x in a)**.5;nb=sum(float(x)**2 for x in b)**.5
  return math.degrees(math.acos(max(-1.,min(1.,dot/(na*nb)))))
 max_normal_angle=max(angular_error(n,v.vector) for n,v in zip(source_normals,obj.data.corner_normals))
 assert max_normal_angle<.05 and max_normal_error<.001,'Baked normal round-trip outside documented precision'
 images={};records=[]
 for channel,size in (('basecolor',2048),('orm',1024),('normal',1024)):
  img,row=bake.bake_channel(obj,channel,size,texdir/('fore09-service-'+channel+'.png'));img.name='fore09-service-'+channel;images[channel]=img;records.append(row);print('FORE09_BAKE',json.dumps(row),flush=True)
 obj.data.materials.clear();mat=bake.baked_material('fore09-service',images);mat.name='BAKED09 / Service PBR';obj.data.materials.append(mat)
 for p in obj.data.polygons:p.material_index=0
 obj.data.calc_loop_triangles()
 for old in hosts:
  o=old.copy();o.data=old.data.copy();o.name='BAKED09 / '+old.name.removeprefix(s.P);col.objects.link(o)
 bpy.data.collections[s.NEW].hide_render=True;bpy.data.collections[s.NEW].hide_viewport=True
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   p=texdir/Path(image.filepath).name
   if not p.exists():assert image.packed_file;p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 blend=a.output/'flagship-fore-surface-09-web.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),compress=True,relative_remap=False)
 assert sha(a.source)==validation['source_sha256']
 report={'revision':'fore-surface-09-bake','source_sha256':sha(a.source),'bake_sha256':sha(blend),'validation_sha256':sha(a.validation),
  'surface_objects':98,'native_hosts':2,'surface_triangles':len(obj.data.loop_triangles),'geometry_vertices_faces_equal':True,'maximum_corner_normal_error':max_normal_error,'maximum_corner_normal_angle_degrees':max_normal_angle,'normal_angle_limit_degrees':.05,'images':records,
  'channels':'Unlit sRGB base color; linear ORM with R=1, G=roughness, B=metallic; tangent normal',
  'limitations':'Fore09 service surfaces baked. Retained broad host paint and older hull remain approximate PBR in GLB. Clearcoat is omitted; AO and lighting are not baked. Browser untested.',
  'source_unchanged':True,'browser_tested':False,'published':False,'device':'CPU','threads':6}
 (a.output/'bake-report.json').write_text(json.dumps(report,indent=2)+'\n');print('FORE09_BAKE_COMPLETE',json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
