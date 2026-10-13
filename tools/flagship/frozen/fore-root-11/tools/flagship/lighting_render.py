"""CPU before/after and GLB readback renders; exact validation required."""
import argparse,json,sys,time
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from surface_gate import require
from surface_finish import sha
from render_study import select_device,peak_process_rss_mib
import build_scene as base
def render(a):
 r=require(a.scene,a.validation);assert r['checks']['declared_lights_only'] and r['checks']['lighting_configuration']
 bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()));scene=bpy.context.scene;col=bpy.data.collections['LIGHT07_SERVICE']
 col.hide_render=a.before or a.neutral
 base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
 if a.web_model:
  for o in bpy.data.objects:
   if o.type=='MESH' and all(c.name!='SPACE' for c in o.users_collection):o.hide_render=True
  previous=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(a.web_model.resolve()));loaded=[o for o in bpy.data.objects if o not in previous]
  for o in loaded:
   if o.parent not in loaded:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 if a.web_lights:
  col.hide_render=True;previous=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(a.web_lights.resolve()));loaded=[o for o in bpy.data.objects if o not in previous]
  for o in loaded:
   if o.parent not in loaded:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
   if o.type=='LIGHT':o.data.energy*=10000
 if a.neutral:
  for o in bpy.data.collections['LIGHTING'].all_objects:o.hide_render=True
  base.light('Inspection key','AREA',(-210,-95,115),(-172,-22,37),42000,(1,1,1),45)
  base.light('Inspection fill','AREA',(-135,-50,57),(-172,-22,37),16000,(.72,.82,1),30)
  base.light('Inspection frontal fill','AREA',(-170,-86,49),(-171,-23,35),35000,(1,1,1),38)
  scene.view_settings.exposure=.65;bpy.data.collections['SPACE'].hide_render=True
 scene.render.resolution_x=a.width;scene.render.resolution_y=a.height;scene.render.resolution_percentage=100
 scene.render.threads_mode='FIXED';scene.render.threads=6;scene.cycles.samples=a.samples;scene.cycles.use_adaptive_sampling=False
 devices=select_device(scene,'cpu');a.output.mkdir(parents=True,exist_ok=True)
 report={'revision':'side-lighting-07','source_sha256':sha(a.scene),'before':a.before,'neutral':a.neutral,
         'web_model_sha256':sha(a.web_model) if a.web_model else None,'web_lights_sha256':sha(a.web_lights) if a.web_lights else None,
         'width':a.width,'height':a.height,'samples':a.samples,'devices':devices,'browser_tested':False,'renders':[]}
 for view in a.views.split(','):
  p=a.output/(view+'.png');assert not p.exists();scene.camera=bpy.data.objects[view];scene.render.filepath=str(p.resolve())
  start=time.perf_counter();bpy.ops.render.render(write_still=True)
  report['renders'].append({'view':view,'seconds':round(time.perf_counter()-start,3),'rss_mib':peak_process_rss_mib()})
  (a.output/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n');print('LIGHT_RENDER',json.dumps(report['renders'][-1]),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--views',default='side03_detail');p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=600);p.add_argument('--samples',type=int,default=32)
 p.add_argument('--neutral',action='store_true');p.add_argument('--before',action='store_true');p.add_argument('--web-model',type=Path);p.add_argument('--web-lights',type=Path);render(p.parse_args())
