"""Fore11 root armor and pinned load-link study, preserving fore10 exactly."""
import argparse,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_scene as base
import finish_study as f
from fore_light_check import require as input_require
from surface_finish import sha
P='FORE11 / ';NEW='FORE11_STRUCTURE';OLD='FORE11_PREVIOUS';CUT='FORE11_CUTTERS'
DEFAULT=Path(__file__).with_name('fore-root-11.json')
INPUT='993d1dfada15902cc4d5d208986fbc0756a9463d771919bcd487deddfae867b2'
CFG={};ANGLE=0
def protected():
 f.PREFIX=P;r=f.protected();r['cameras']={k:v for k,v in r['cameras'].items() if not k.startswith(P)};return r
def point(u,v,z):
 c,s=math.cos(ANGLE),math.sin(ANGLE);cx,cy=CFG['opening_center'];return Vector((cx+c*u-s*v,cy+s*u+c*v,z))
def finish(o,kind):
 o['revision']='fore-root-11';o['root_kind']=kind;o['role']='hull'
 if o.type=='MESH':
  bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
 return o
def contact(o,target,p):
 rows=json.loads(o.get('root_contacts','[]'));rows.append({'target':target.name,'point':list(p)});o['root_contacts']=json.dumps(rows);return o
def box(name,p,d,mat='frame',edge=.055,local=False,kind='frame'):
 o=base.box(P+name,point(*p) if local else p,d,mat,NEW,edge)
 if local:o.rotation_euler.z=ANGLE
 return finish(o,kind)
def chamfer(u,v,c):return [(-u+c,-v),(u-c,-v),(u,-v+c),(u,v-c),(u-c,v),(-u+c,v),(-u,v-c),(-u,-v+c)]
def prism(name,uv,lo,hi,mat='frame',edge=.06,kind='frame'):
 return finish(base.prism(P+name,[tuple(point(u,v,0)[:2]) for u,v in uv],lo,hi,mat,NEW,edge),kind)
def cylinder(name,uvz,r,depth,mat='metal',axis='Z',kind='fastener'):
 o=base.cylinder(P+name,point(*uvz),r,depth,mat,axis,NEW,vertices=24)
 if axis=='Y':o.rotation_euler=(Matrix.Rotation(ANGLE,4,'Z')@Matrix.Rotation(math.pi/2,4,'X')).to_euler()
 return finish(o,kind)
def ring(name,outer,inner,lo,hi,mat='armor'):
 n=len(outer);assert len(inner)==n;vs=[point(u,v,z) for z in (lo,hi) for poly in (outer,inner) for u,v in poly];faces=[]
 for i in range(n):
  j=(i+1)%n
  faces.extend([(i,j,2*n+j,2*n+i),(n+i,3*n+i,3*n+j,n+j),(2*n+i,2*n+j,3*n+j,3*n+i),(i,n+i,n+j,j)])
 mesh=bpy.data.meshes.new(P+name);mesh.from_pydata(vs,[],faces);mesh.update();o=bpy.data.objects.new(P+name,mesh);bpy.data.collections[NEW].objects.link(o);mesh.materials.append(base.MATERIALS[mat]);base.bevel(o,.045);return finish(o,'rim')
def lug(name,u,v):
 profile=[(u-1.25,22.43),(u+1.25,22.43),(u+1.08,23.83),(u+.66,24.15),(u-.66,24.15),(u-1.08,23.83)];n=len(profile)
 vs=[point(x,v+side*.35,z) for side in (-1,1) for x,z in profile];fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
 m=bpy.data.meshes.new(P+name);m.from_pydata(vs,[],fs);m.update();o=bpy.data.objects.new(P+name,m);bpy.data.collections[NEW].objects.link(o);m.materials.append(base.MATERIALS['frame']);base.bevel(o,.08);return finish(o,'clevis')
def tool(o):
 for c in list(o.users_collection):c.objects.unlink(o)
 bpy.data.collections[CUT].objects.link(o);o.hide_render=True;o.display_type='WIRE';return o
def boolean(o,cutter,operation):
 m=o.modifiers.new('Editable '+operation.lower(),'BOOLEAN');m.operation=operation;m.solver='EXACT';m.object=cutter;o.modifiers.move(len(o.modifiers)-1,0)
def build(a):
 global CFG,ANGLE
 input_require(a.source,a.validation);CFG=json.loads(a.config.read_text());ANGLE=math.radians(CFG['opening_angle_degrees'])
 assert sha(a.source)==INPUT==CFG['input_sha256'] and not a.output.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));before=protected();base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
 for c in (NEW,OLD,CUT):base.collection(c)
 for key,old in [('armor','STUDY_light_paint'),('frame','FORE09 / casing'),('bed','FORE09 / bed'),('metal','FORE09 / metal'),('seal','FORE09 / rubber')]:
  mat=bpy.data.materials[old].copy();mat.name=P+key;base.MATERIALS[key]=mat
 original=bpy.data.objects[CFG['removed_object']];body=bpy.data.objects[CFG['body']];removed=[CFG['removed_object']]+CFG['removed_overlays'];bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 x0,x1=CFG['seams_x'];gap=CFG['seam_width']/2
 limits=[(-300,x0-gap),(x0+gap,x1-gap),(x1+gap,-100)];plates=[]
 for i,(lo,hi) in enumerate(limits):
  clip=tool(box('Armor segment clipping tool '+str(i+1),((lo+hi)/2,-50,25),(hi-lo,130,100),'bed',0,kind='tool'))
  o=original.copy();o.data=bpy.data.meshes.new_from_object(original.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg);o.name=P+['Forward armor segment','Service armor segment','Heel armor segment'][i];bpy.data.collections[NEW].objects.link(o)
  for mod in list(o.modifiers):o.modifiers.remove(mod)
  o.data.materials.clear();o.data.materials.append(base.MATERIALS['armor']);finish(o,'armor');boolean(o,clip,'INTERSECT');o['source_evaluated_copy']=original.name;plates.append(o)
 hole=tool(prism('Root inspection opening tool',chamfer(*CFG['opening_half_extent'],CFG['opening_chamfer']),20.8,28,'bed',0,'tool'));boolean(plates[1],hole,'DIFFERENCE')
 for name in removed:
  old=bpy.data.objects[name]
  for c in list(old.users_collection):c.objects.unlink(old)
  bpy.data.collections[OLD].objects.link(old)
 for c in (OLD,CUT):bpy.data.collections[c].hide_render=True;bpy.data.collections[c].hide_viewport=True
 # Shared seats bridge each armor joint and sink into the unchanged shoulder shell.
 for i,x in enumerate(CFG['seams_x']):
  for j,y in enumerate((-41,-53)):
   seat=box(f'Joint {i+1} common seat {j+1}',(x,y,22.30),(2.4,3.8,1.0),'frame',.09)
   contact(seat,body,(x,y,21.93));contact(plates[i],seat,(x-.70,y,22.40));contact(plates[i+1],seat,(x+.70,y,22.40))
 # Actual open recess: a shallow pan, retained armor wall and fitted retaining rim.
 pan=prism('Root inspection pan',chamfer(7.94,3.84,.66),21.83,22.20,'bed',.055,'pan');contact(pan,body,point(0,0,21.95))
 rim=ring('Root opening retaining rim',chamfer(8.55,4.45,1.25),chamfer(8,3.9,.7),24.82,25.13)
 contact(rim,plates[1],point(0,4.20,24.94));contact(rim,plates[1],point(0,-4.20,24.94))
 for sign in (-1,1):
  rail=box('Pan edge stiffener '+str(sign),(0,sign*2.83,22.35),(14.8,.38,.52),'frame',.055,True)
  contact(rail,pan,point(0,sign*2.83,22.15))
 pins=[]
 for i,u in enumerate((-6.0,6.0)):
  foot=box(f'Clevis {i+1} seated base',(u,0,22.34),(3.25,3.70,.42),'frame',.085,True,'mount');contact(foot,pan,point(u,0,22.16))
  cheeks=[]
  for j,v in enumerate((-1.18,1.18)):
   cheek=lug(f'Clevis {i+1} cheek {j+1}',u,v);contact(cheek,foot,point(u,v,22.48));cheeks.append(cheek)
  pin=cylinder(f'Clevis {i+1} captive transverse pin',(u,0,23.52),.32,3.40,'metal','Y','pin');pins.append(pin)
  for cheek,v in zip(cheeks,(-1.18,1.18)):contact(pin,cheek,point(u,v,23.52))
  for sign in (-1,1):
   washer=cylinder(f'Clevis {i+1} pin retainer {sign}',(u,sign*1.54,23.52),.47,.18,'metal','Y');contact(washer,pin,point(u,sign*1.54,23.52))
  for du in (-1.15,1.15):
   for v in (-1.63,1.63):
    lock=cylinder(f'Clevis {i+1} base lock {du} {v}',(u+du,v,22.58),.13,.17);contact(lock,foot,point(u+du,v,22.51))
 link=box('Captured longitudinal shear link',(0,0,23.52),(12.90,1.28,.68),'metal',.09,True,'load_link')
 for pin,u in zip(pins,(-6.0,6.0)):contact(link,pin,point(u,0,23.52))
 # Sparse captive armor locks are grouped at shared seats, not spread over the hull.
 for i,(x,y) in enumerate(((-204.4,-41),(-204.4,-53),(-201.6,-41),(-201.6,-53),(-178.1,-41),(-178.1,-53))):
  o=finish(base.cylinder(P+'Armor captive lock '+str(i+1),(x,y,25.06),.25,.25,'metal','Z',NEW,vertices=20),'fastener')
  contact(o,plates[0 if x<x0 else (1 if x<x1 else 2)],(x,y,24.98))
 # The existing turret footing keeps its support surface at z=25.
 plates[0]['root_turret_seat_preserved']=True
 for name,d in CFG['cameras'].items():
  cam=base.camera(P+name,d['position'],d['target'],lens=d['lens']);cam.data.clip_end=100000000
 bpy.context.view_layer.update();assert protected()==before,'Prior geometry, material, light or camera changed'
 scene=bpy.context.scene;scene.name='KUHAI — Forward Root Structure 11';scene['revision']='fore-root-11';scene['root11_config_sha256']=sha(a.config);scene['root11_input_sha256']=INPUT
 scene.camera=bpy.data.objects[P+'root11_detail'];a.output.parent.mkdir(parents=True,exist_ok=True)
 for im in bpy.data.images:
  if im.type=='IMAGE' and im.users:
   assert im.packed_file;p=a.output.parent/'textures'/Path(im.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(im.packed_file.data);im.filepath='//textures/'+p.name
   for packed in im.packed_files:packed.filepath=im.filepath
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 r={'revision':'fore-root-11','source_sha256':sha(a.output),'input_sha256':INPUT,'config_sha256':sha(a.config),'visible_new_meshes':len(bpy.data.collections[NEW].objects),'removed_visible_objects':removed,'new_cameras':CFG['cameras'],'browser_tested':False,'published':False,'official_replica':False}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);build(p.parse_args())
