"""Matched atmosphere render of real mesh + light GLBs, CPU only, not WebGL."""
import argparse,json,sys,time
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fore_light_check import require
from surface_finish import sha
from render_study import select_device,peak_process_rss_mib

def main(a):
 require(a.source,a.validation);profile=json.loads((a.assets/'service-lighting.json').read_text());assert profile['model_sha256']==sha(a.assets/'flagship.glb') and profile['lights_sha256']==sha(a.assets/'service-lights.glb');assert not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.context.scene
 # Replace ship meshes and local service lights, retaining the exact space/key rig.
 for o in bpy.data.objects:
  if o.type=='MESH' and not any(c.name=='SPACE' for c in o.users_collection):o.hide_render=True
 for col in ('LIGHT07_SERVICE','FORE10_LIGHTS'):bpy.data.collections[col].hide_render=True
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str((a.assets/'flagship.glb').resolve()));new=set(bpy.data.objects)-before
 for o in new:
  if o.parent not in new:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str((a.assets/'service-lights.glb').resolve()),export_import_convert_lighting_mode='SPEC');lights=set(bpy.data.objects)-before
 for o in lights:
  if o.parent not in lights:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
  if o.type=='LIGHT':o.data.energy*=10000;o.data.shadow_soft_size=0
 # Finite radii are deliberately not restored: show the actual punctual limit.
 scene.camera=bpy.data.objects['FORE08 / fore08_detail'];scene.render.resolution_x=960;scene.render.resolution_y=600;scene.render.resolution_percentage=100
 scene.render.threads_mode='FIXED';scene.render.threads=6;scene.cycles.samples=32;scene.cycles.use_adaptive_sampling=False;select_device(scene,'cpu')
 a.output.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(a.output.resolve());start=time.perf_counter();bpy.ops.render.render(write_still=True)
 r={'source_sha256':sha(a.source),'model_sha256':sha(a.assets/'flagship.glb'),'lights_sha256':sha(a.assets/'service-lights.glb'),'image_sha256':sha(a.output),'seconds':round(time.perf_counter()-start,3),'rss_mib':peak_process_rss_mib(),'device':'CPU','width':960,'height':600,'samples':32,'threads':6,'browser_tested':False,'note':'Actual compressed mesh and KHR punctual light GLBs decoded into Blender. Original finite radii not restored; shadows differ. Not browser/Three performance evidence.'}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
