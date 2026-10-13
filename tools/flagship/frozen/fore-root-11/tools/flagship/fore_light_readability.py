"""Visible-surface pixel samples in matched CPU images; not lux/FPS claims."""
import argparse,json,sys
from pathlib import Path
import bpy,numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fore_check import visible
from check_fore_web_geometry import world_tree
from lighting_readability import image_pixels
from surface_finish import sha
def main(a):
 bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()));scene=bpy.context.scene;cam=bpy.data.objects['FORE08 / fore08_detail'];tree=world_tree(visible().values())
 before=image_pixels(a.before);after=image_pixels(a.after);assert before.shape==after.shape;h,w=before.shape[:2];scene.render.resolution_x=w;scene.render.resolution_y=h
 groups={}
 for label,x in (('U1 casing',-205.8),('U2 casing',-195.4)):
  groups[label]=[(x-1.6+3.2*i/12,-80.155,21.45+1.95*j/12) for i in range(13) for j in range(13)]
 groups['Central floor']=[(-202.3+3.5*i/16,-81.5+6.5*j/16,19.503) for i in range(17) for j in range(17)]
 groups['Coolant interconnect']=[(-202.3+3.4*i/30,-79.2,22.12) for i in range(31)]
 rows=[]
 for label,points in groups.items():
  pixels=set()
  for p in points:
   p=Vector(p);delta=p-cam.location;hit=tree.ray_cast(cam.location,delta.normalized(),delta.length+.1)
   if hit[0] is None or (hit[0]-p).length>.12:continue
   q=world_to_camera_view(scene,cam,p);px=int(q.x*w);py=int(q.y*h)
   if 0<=px<w and 0<=py<h:pixels.add((py,px))
  assert len(pixels)>=5,'No useful visible samples for '+label
  old=np.array([before[y,x,:3] for y,x in pixels])@np.array((.2126,.7152,.0722));new=np.array([after[y,x,:3] for y,x in pixels])@np.array((.2126,.7152,.0722))
  rows.append({'region':label,'visible_unique_pixels':len(pixels),'before_encoded_luma_255':round(float(old.mean()*255),2),'after_encoded_luma_255':round(float(new.mean()*255),2),'ratio':round(float(new.mean()/old.mean()),3),'clipped_samples':int(sum(new>.98))})
 r={'scene_sha256':sha(a.scene),'before_image_sha256':sha(a.before),'after_image_sha256':sha(a.after),'view':'fore08_detail','regions':rows,'note':'Ray-filtered projected surface pixels; relative encoded image brightness only. Not illuminance, browser rendering or art acceptance.','browser_tested':False}
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
