"""Matched source previews of the fore11 root; CPU only."""
import argparse,json,sys,time
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_scene as base
import fore_root as s
from fore_root_check import require
from surface_finish import sha
from render_study import select_device,peak_process_rss_mib
def render(a):
 require(a.scene,a.validation);bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()));scene=bpy.context.scene;base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
 # A reproducible macro inspection camera is added only in memory for this render.
 extra={'root11_joint':{'position':[-215,-78,64],'target':[-191.5,-49.7,23.7],'lens':70}}
 for name in a.views.split(','):
  if name in extra:
   d=extra[name];cam=base.camera(s.P+name,d['position'],d['target'],lens=d['lens']);cam.data.clip_end=100000000
 if a.before:bpy.data.collections[s.NEW].hide_render=True;bpy.data.collections[s.OLD].hide_render=False
 if a.neutral:
  for name in ('LIGHTING','LIGHT07_SERVICE','ROOM_LIGHTS','FORE10_LIGHTS','SPACE'):bpy.data.collections[name].hide_render=True
  base.collection('FORE11_INSPECTION_LIGHTS')
  base.light('Root inspection key','AREA',(-242,-158,140),(-197,-50,22),360000,(1,1,1),75,group='FORE11_INSPECTION_LIGHTS')
  base.light('Root inspection fill','AREA',(-156,-65,95),(-197,-50,22),140000,(.8,.87,1),55,group='FORE11_INSPECTION_LIGHTS');scene.view_settings.exposure=.65
 scene.render.resolution_x=a.width;scene.render.resolution_y=a.height;scene.render.resolution_percentage=100;scene.render.threads_mode='FIXED';scene.render.threads=6;scene.cycles.samples=a.samples;scene.cycles.use_adaptive_sampling=False;select_device(scene,'cpu');a.output.mkdir(parents=True,exist_ok=True)
 r={'revision':'fore-root-11','source_sha256':sha(a.scene),'before':a.before,'neutral':a.neutral,'width':a.width,'height':a.height,'samples':a.samples,'threads':6,'device':'CPU','browser_tested':False,'temporary_cameras':{k:v for k,v in extra.items() if k in a.views.split(',')},'renders':[]}
 for name in a.views.split(','):
  path=a.output/(name+'.png');assert not path.exists();camera=s.P+name if s.P+name in bpy.data.objects else ('FORE08 / '+name if 'FORE08 / '+name in bpy.data.objects else name)
  scene.camera=bpy.data.objects[camera];scene.render.filepath=str(path.resolve());start=time.perf_counter();bpy.ops.render.render(write_still=True)
  r['renders'].append({'view':name,'image_sha256':sha(path),'seconds':round(time.perf_counter()-start,3),'rss_mib':peak_process_rss_mib()});(a.output/'benchmark.json').write_text(json.dumps(r,indent=2)+'\n');print('FORE11_RENDER',json.dumps(r['renders'][-1]),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--views',default='root11_detail');p.add_argument('--neutral',action='store_true');p.add_argument('--before',action='store_true');p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=600);p.add_argument('--samples',type=int,default=32);render(p.parse_args())
