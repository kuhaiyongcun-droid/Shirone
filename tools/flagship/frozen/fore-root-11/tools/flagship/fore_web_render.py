"""One CPU inspection of the actual decoded GLB. This is NOT browser QA."""
import argparse,json,sys,time
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_scene as base
from surface_finish import sha
from fore_surface_check import require
from render_study import select_device,peak_process_rss_mib

def main(a):
 require(a.source,a.validation);manifest=json.loads((a.assets/'model-manifest.json').read_text())
 assert sha(a.assets/'flagship.glb')==manifest['files']['flagship.glb']['sha256'];assert not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.context.scene
 for o in bpy.data.objects:
  if o.type=='MESH':o.hide_render=True
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str((a.assets/'flagship.glb').resolve()));new=set(bpy.data.objects)-before
 for o in new:
  if o.parent not in new:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 for name in ('LIGHTING','LIGHT07_SERVICE','ROOM_LIGHTS','SPACE'):bpy.data.collections[name].hide_render=True
 base.COLLECTIONS.update({c.name:c for c in bpy.data.collections});base.collection('FORE08_INSPECTION_LIGHTS')
 base.light('Fore inspection key','AREA',(-242,-158,140),(-199,-80,22),360000,(1,1,1),75,group='FORE08_INSPECTION_LIGHTS')
 base.light('Fore inspection fill','AREA',(-156,-65,95),(-199,-80,22),140000,(.8,.87,1),55,group='FORE08_INSPECTION_LIGHTS')
 scene.view_settings.exposure=.65;scene.camera=bpy.data.objects['FORE08 / fore08_detail'];scene.render.resolution_x=960;scene.render.resolution_y=600;scene.render.resolution_percentage=100
 scene.render.threads_mode='FIXED';scene.render.threads=6;scene.cycles.samples=32;scene.cycles.use_adaptive_sampling=False;select_device(scene,'cpu')
 a.output.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(a.output.resolve());start=time.perf_counter();bpy.ops.render.render(write_still=True)
 report={'source_sha256':sha(a.source),'glb_sha256':sha(a.assets/'flagship.glb'),'image_sha256':sha(a.output),'device':'CPU','samples':32,'threads':6,'width':960,'height':600,'seconds':round(time.perf_counter()-start,3),'rss_mib':peak_process_rss_mib(),'browser_tested':False,'note':'Actual compressed GLB decoded into Blender and rendered under the matched neutral rig. Checks conversion appearance, not WebGL or device performance.'}
 a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
