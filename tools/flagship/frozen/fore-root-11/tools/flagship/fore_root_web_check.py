"""Decoded GLB rays protect both equipment recesses and the new load-link opening."""
import argparse,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_root as s
from fore_root_check import require
from fore_check import visible
from check_fore_web_geometry import world_tree,casts
from surface_finish import sha
def main(a):
 r=require(a.source,a.validation);cfg=json.loads(a.config.read_text());assert r['config_sha256']==sha(a.config);s.CFG=cfg;s.ANGLE=math.radians(cfg['opening_angle_degrees'])
 m=json.loads((a.assets/'model-manifest.json').read_text());assert sha(a.assets/'flagship.glb')==m['files']['flagship.glb']['sha256'] and m['editable_source_sha256']==sha(a.source)
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));world=world_tree(visible().values());samples=[]
 def row(view,target,origin,points):samples.append({'view':view,'target':target,'origin':list(origin),'points':[list(p) for p in points],'source_hits':casts(world,origin,points)})
 for camera in ('fore08_detail','fore08_reverse'):
  origin=bpy.data.objects['FORE08 / '+camera].location
  for i,x in enumerate((-205.8,-195.4)):row(camera,'fore09 U'+str(i+1)+' lid',origin,[(x-1.56+3.12*a/10,-79.1+1.8*b/10,24.142) for a in range(11) for b in range(11)])
  row(camera,'fore09 channel floor',origin,[(-201.75+i*.55,-80.8+j*.7,19.502) for i in range(5) for j in range(7)])
 for camera in cfg['cameras']:
  origin=bpy.data.objects[s.P+camera].location
  row(camera,'fore11 load link',origin,[s.point(-4.4+8.8*i/16,-.25+.5*j/4,23.863) for i in range(17) for j in range(5)])
  row(camera,'fore11 inspection pan',origin,[s.point(u,v,22.203) for u in (-3.5,-1.75,0,1.75,3.5) for v in (-2.2,2.2)])
 for x in cfg['seams_x']:
  for y in (-41,-53):row('vertical','shared armor seat',(x,y,26),[(x,y,21)])
 del world
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str((a.assets/'flagship.glb').resolve()))
 for o in bpy.context.scene.objects:
  if o.parent is None:o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
 world=world_tree(list(bpy.context.scene.objects));rows=[]
 for item in samples:
  actual=casts(world,item['origin'],item['points']);errors=[(Vector(x)-Vector(y)).length if x is not None and y is not None else None for x,y in zip(item['source_hits'],actual)];good=sum(e is not None and e<.1 for e in errors)
  rows.append({'view':item['view'],'target':item['target'],'rays':len(errors),'within_0_1_source_m':good,'max_error_source_m':max((e for e in errors if e is not None),default=None),'passed':good==len(errors)})
 report={'source_sha256':sha(a.source),'glb_sha256':sha(a.assets/'flagship.glb'),'rows':rows,'total_rays':sum(x['rays'] for x in rows),'passed':len(rows)==14 and all(x['passed'] for x in rows),'browser_tested':False,'scope':'Two old fore09 cameras plus two root11 cameras and four vertical seam samples. Actual Draco-decoded GLB, no browser.'}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True);assert report['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=s.DEFAULT);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
