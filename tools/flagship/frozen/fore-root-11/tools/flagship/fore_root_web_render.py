"""Actual GLB + unchanged six-light rig readback under matched root atmosphere."""
import argparse,json,sys,time
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fore_root_check import require
from surface_finish import sha
from render_study import select_device,peak_process_rss_mib
def main(a):
 require(a.source,a.validation);profile=json.loads((a.assets/'service-lighting.json').read_text());assert profile['model_sha256']==sha(a.assets/'flagship.glb') and profile['lights_sha256']==sha(a.assets/'service-lights.glb') and not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.context.scene
 for o in bpy.data.objects:
  if o.type=='MESH' and not any(c.name=='SPACE' for c in o.users_collection):o.hide_render=True
 for c in ('LIGHT07_SERVICE','FORE10_LIGHTS'):bpy.data.collections[c].hide_render=True
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str((a.assets/'flagship.glb').resolve()));obs=set(bpy.data.objects)-before
 for o in obs:
  if o.parent not in obs:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str((a.assets/'service-lights.glb').resolve()),export_import_convert_lighting_mode='SPEC');obs=set(bpy.data.objects)-before
 for o in obs:
  if o.parent not in obs:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
  if o.type=='LIGHT':o.data.energy*=10000;o.data.shadow_soft_size=0
 scene.camera=bpy.data.objects['FORE11 / root11_detail'];scene.render.resolution_x=960;scene.render.resolution_y=600;scene.render.resolution_percentage=100;scene.render.threads_mode='FIXED';scene.render.threads=6;scene.cycles.samples=32;scene.cycles.use_adaptive_sampling=False;select_device(scene,'cpu')
 a.output.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(a.output.resolve());start=time.perf_counter();bpy.ops.render.render(write_still=True)
 r={'source_sha256':sha(a.source),'model_sha256':sha(a.assets/'flagship.glb'),'lights_sha256':sha(a.assets/'service-lights.glb'),'image_sha256':sha(a.output),'seconds':round(time.perf_counter()-start,3),'rss_mib':peak_process_rss_mib(),'device':'CPU','width':960,'height':600,'samples':32,'threads':6,'browser_tested':False,'note':'Actual mesh and six-light GLBs decoded into Blender. Finite source radii not restored. Simple PBR approximates new regional materials. Not browser or performance evidence.'}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
