"""Measure fixed projected panel samples in matched renders; not art acceptance."""
import argparse,json,sys
from pathlib import Path
import bpy,numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
def image_pixels(path):
 i=bpy.data.images.load(str(path.resolve()),check_existing=False);i.colorspace_settings.name='Non-Color';i.reload()
 a=np.empty(len(i.pixels),dtype=np.float32);i.pixels.foreach_get(a);return a.reshape((i.size[1],i.size[0],4))
def main(a):
 bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()));scene=bpy.context.scene;scene.render.resolution_x=960;scene.render.resolution_y=600
 cam=bpy.data.objects['side03_detail'];before=image_pixels(a.before);after=image_pixels(a.after);assert before.shape==after.shape
 rows=[]
 for base,label in (('Inset module face','E'),('Canister instrument saddle','P')):
  for i in range(3):
   o=bpy.data.objects['SIDE06 / '+base+('' if i==0 else '.'+str(i).zfill(3))]
   corners=[Vector(v) for v in o.bound_box];lo=Vector(tuple(min(v[k] for v in corners) for k in range(3)));hi=Vector(tuple(max(v[k] for v in corners) for k in range(3)))
   pts=[]
   for x in range(9):
    for z in range(9):
     v=o.matrix_world@Vector((lo.x+(hi.x-lo.x)*(.15+.7*x/8),lo.y-.002,lo.z+(hi.z-lo.z)*(.15+.7*z/8)))
     q=world_to_camera_view(scene,cam,v);px=int(q.x*960);py=int(q.y*600);assert 0<=px<960 and 0<=py<600;pts.append((py,px))
   old=np.array([before[y,x,:3] for y,x in pts])@np.array((.2126,.7152,.0722))
   new=np.array([after[y,x,:3] for y,x in pts])@np.array((.2126,.7152,.0722))
   rows.append({'panel':label+str(i+1),'sample_count':len(pts),'before_mean_encoded_luma_255':round(float(old.mean()*255),2),
    'after_mean_encoded_luma_255':round(float(new.mean()*255),2),'ratio':round(float(new.mean()/old.mean()),3),'after_clipped_samples':int(sum(new>.98))})
 r={'view':'side03_detail','panels':rows,'interpretation':'Relative encoded-pixel readability measurement in matched CPU images; not photometric lux, browser evidence or final art acceptance.'}
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
