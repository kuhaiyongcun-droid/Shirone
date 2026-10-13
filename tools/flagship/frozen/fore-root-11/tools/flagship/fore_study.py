"""Fore08: a real recessed port-shoulder service cassette and terminal load links.

Original project interpretation. Exact lighting07 input; no original datablocks
overwritten. Prior shoulder parts are retained in a hidden comparison collection.
"""
import argparse, json, sys, math
from pathlib import Path
import bpy, bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_scene as base
import side_study as s
import finish_study as f
import assembly_check as acheck
from surface_finish import sha
from surface_gate import require

P='FORE08 / ';NEW='FORE08_STRUCTURE';OLD='FORE08_PREVIOUS';CUT='FORE08_CUTTERS'
INPUT='e3854304e9a2b4ffe01cccb0b8d96daf52bd6f5f5af9a20d8cb73a6f47c7801c'
HOSTS=['FORM03 / Swept forward shoulder body','FORM03 / Forward outer armor island']
REMOVED=HOSTS+['FORM03 / Fore armor maintenance recess'+('' if i==0 else f'.{i:03}') for i in range(3)]
CAMERAS={
 'fore08_detail':{'position':[-229,-115,81],'target':[-201,-78,23],'lens':63},
 'fore08_reverse':{'position':[-172,-114,75],'target':[-201,-78,23],'lens':61},
 'fore08_context':{'position':[-330,-277,188],'target':[-200,-49,23],'lens':61},
}
CORNER_JOINTS=[
 ['Fore pressure bulkhead','Outboard continuous sill',[-211.65,-82.70,23.2]],
 ['Fore pressure bulkhead','Inboard continuous sill',[-211.65,-73.80,23.2]],
 ['Aft pressure bulkhead','Outboard continuous sill',[-189.35,-82.70,23.2]],
 ['Aft pressure bulkhead','Inboard continuous sill',[-189.35,-73.80,23.2]],
]

def protected():
 f.PREFIX=P;r=f.protected()
 r['cameras']={k:v for k,v in r['cameras'].items() if not k.startswith(P)}
 return r

def finish(o,kind='structure',group=None):
 o=s.finish(o,kind);o['revision']='fore-structure-08';o['fore_kind']=kind
 if group:o['fore_group']=group
 return o

def box(name,loc,dims,mat='s_paint',edge=.06,kind='structure',group=None):
 return finish(base.box(name,loc,dims,mat,NEW,edge),kind,group)

def prism(name,xy,lo,hi,mat='s_paint',edge=.06,kind='structure',group=None):
 return finish(base.prism(name,xy,lo,hi,mat,NEW,edge),kind,group)

def cylinder(name,p,r,depth,mat='s_metal',axis='Z',kind='fitting',group=None):
 return finish(base.cylinder(name,p,r,depth,mat,axis,NEW,vertices=24),kind,group)

def support(name,start,end,width,depth,ta,tb,mat='s_service'):
 o=s.beam(name,start,end,width,depth,mat)
 o['fore_kind']='mount';o['fore_support_points']=json.dumps([list(start),list(end)])
 o['fore_start_target']=ta.name;o['fore_end_target']=tb.name
 return o

def route(name,points,r,ta,tb,mat='s_pipe'):
 o=s.pipe(name,points,r,mat);o['fore_kind']='route'
 o['fore_route_points']=json.dumps([list(p) for p in points]);o['fore_radius']=r
 o['fore_start_target']=ta.name;o['fore_end_target']=tb.name
 return o

def attached(o,target,p):
 o['fore_attachment_target']=target.name;o['fore_attachment_point']=json.dumps(list(p))
 return o

def chamfer_rect(x0,x1,y0,y1,c=.5):
 return [(x0+c,y0),(x1-c,y0),(x1,y0+c),(x1,y1-c),
         (x1-c,y1),(x0+c,y1),(x0,y1-c),(x0,y0+c)]

def move_old(o):
 for c in list(o.users_collection):c.objects.unlink(o)
 bpy.data.collections[OLD].objects.link(o)

def build(a):
 gate=require(a.source,a.validation)
 assert gate['checks']['lighting_configuration'] and sha(a.source)==INPUT
 assert not a.output.exists(),'Use a new output path'
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));before=protected()
 base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
 for name in (NEW,OLD,CUT):base.collection(name)
 s.NEW,s.PREFIX=NEW,P;s.PARTS=[]
 for key in ('s_paint','s_service','s_dark','s_metal','s_pipe','s_seal','s_mark','s_label','s_ivory','s_repair'):
  base.MATERIALS[key]=bpy.data.materials['SIDE06 / '+key]
 cutter=prism('Service aperture tool',chamfer_rect(-212,-189,-83,-73.5,.65),18.9,29,'s_dark',0)
 for c in list(cutter.users_collection):c.objects.unlink(cutter)
 bpy.data.collections[CUT].objects.link(cutter);cutter.hide_render=True;cutter.display_type='WIRE'
 replacements={}
 for name in HOSTS:
  old=bpy.data.objects[name];o=old.copy();o.data=old.data.copy();o.name=P+name.removeprefix('FORM03 / ')
  bpy.data.collections[NEW].objects.link(o);o['fore_kind']='host';o['source_object']=name
  bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
  mod=o.modifiers.new('Editable recessed service channel','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
  o.modifiers.move(len(o.modifiers)-1,0);replacements[name]=o
 for name in REMOVED:move_old(bpy.data.objects[name])
 for name in (OLD,CUT):bpy.data.collections[name].hide_render=True;bpy.data.collections[name].hide_viewport=True

 # The pan overlaps the uncut floor by 0.1 m; the wall reveals real armor depth.
 bed=prism('Sealed channel bed',chamfer_rect(-211.85,-189.15,-82.85,-73.65,.55),18.8,19.5,'s_dark',.08)
 attached(bed,replacements[HOSTS[0]],(-201,-78,18.85))
 walls=[]
 for name,p,d in [('Inboard continuous sill',(-200.5,-73.78,22.7),(22.4,.42,6.7)),
                  ('Outboard continuous sill',(-200.5,-82.72,22.7),(22.4,.42,6.7)),
                  ('Fore pressure bulkhead',(-211.67,-78.25,22.7),(.44,9.1,6.7)),
                  ('Aft pressure bulkhead',(-189.33,-78.25,22.7),(.44,9.1,6.7))]:
  o=box(name,p,d,'s_service',.05);walls.append(o);attached(o,bed,(p[0],p[1],19.42))
 # Narrow top flanges seat on the surrounding armor; no floating decorative tiles.
 for y in (-83.05,-73.45):
  lip=box('Armor opening retaining flange',(-200.5,y,25.85),(22.4,.75,.32),'s_paint',.045)
  attached(lip,replacements[HOSTS[1]],(-201,y-.1 if y<-80 else y+.1,25.8))
 for x in (-211.9,-189.1):
  box('End flange',(x,-78.25,25.85),(.65,8.8,.32),'s_paint',.045)
 for x in (-210.8,-202,-191):
  for y in (-82.9,-73.6):
   cylinder('Captive rim locking pin',(x,y,26.07),.17,.18,'s_metal')

 units=[];ports=[]
 for i,x in enumerate((-205.8,-195.4)):
  group=f'U{i+1}'
  # Cast body with broad chamfers, separate seal/lid and cooling shoulders.
  body=prism(f'{group} conditioning casing',chamfer_rect(x-3,x+3,-80.15,-76.25,.65),21.0,23.75,'s_paint',.16,'equipment',group)
  units.append(body)
  seal=prism(f'{group} lid gasket',chamfer_rect(x-2.67,x+2.67,-79.78,-76.62,.4),23.68,23.85,'s_seal',.025,'equipment',group)
  lid=prism(f'{group} removable top panel',chamfer_rect(x-2.6,x+2.6,-79.7,-76.7,.37),23.81,24.14,'s_repair' if i else 's_service',.075,'equipment',group)
  lid['fore_inspection_panel']=True
  for dx in (-2.1,2.1):
   for y in (-79.65,-76.75):
    support(f'{group} bolted support', (x+dx,y,19.3),(x+dx,y,21.3),.45,.65,bed,body)
    cylinder(f'{group} lid quarter-turn pin',(x+dx,y,24.18),.13,.13,'s_metal',group=group)
  for dx in (-2.2,-1.45,-.7,.05,.8,1.55,2.3):
   for y in (-80.04,-76.36):
    box(f'{group} cast cooling rib',(x+dx,y,22.5),(.18,.44,1.5),'s_service',.035,'equipment',group)
  box(f'{group} recessed status plate',(x-.2,-78.2,24.18),(2.0,.65,.08),'s_dark',.035,'equipment',group)
  box(f'{group} identity stripe',(x+.88,-78.2,24.18),(.18,.62,.07),'s_mark',.02,'equipment',group)
  for dx in (-1.55,1.55):
   points=[(x+dx-.32,-78.2,24.04),(x+dx-.32,-78.2,24.43),
           (x+dx+.32,-78.2,24.43),(x+dx+.32,-78.2,24.04)]
   handle=route(f'{group} attached lifting handle',points,.055,lid,lid,'s_metal');handle['fore_kind']='handle'
  pair=[]
  for sign in (-1,1):
   loc=(x+sign*2.98,-79.08,22.05)
   flange=cylinder(f'{group} fluid flange',loc,.38,.3,'s_service','X',group=group)
   attached(flange,body,(x+sign*2.88,-79.08,22.05))
   socket=cylinder(f'{group} fluid union',(x+sign*3.18,-79.08,22.05),.25,.48,'s_metal','X',group=group)
   attached(socket,flange,loc);pair.append(socket)
  ports.append(pair)
  power=cylinder(f'{group} power gland',(x,-76.18,21.95),.26,.48,'s_seal','Y',group=group)
  attached(power,body,(x,-76.36,21.95));ports[-1].append(power)

 # Bulkhead ports deliberately overlap their wall by 0.14 m.
 inlet=cylinder('Supply bulkhead sleeve',(-211.5,-79.08,22.05),.31,.72,'s_metal','X')
 outlet=cylinder('Return bulkhead sleeve',(-189.5,-79.08,22.05),.31,.72,'s_metal','X')
 attached(inlet,walls[2],(-211.68,-79.08,22.05));attached(outlet,walls[3],(-189.32,-79.08,22.05))
 links=[(inlet,ports[0][0]),(ports[0][1],ports[1][0]),(ports[1][1],outlet)]
 for i,(a0,b0) in enumerate(links):
  start=a0.location.copy();end=b0.location.copy()
  route(f'Closed coolant link {i+1}',[start,end],.14,a0,b0)
 # Each cable leaves an independent bulkhead connector and bends into a gland.
 for i,x in enumerate((-205.8,-195.4)):
  wallport=cylinder(f'U{i+1} sealed wall power socket',(x,-74.0,21.95),.24,.65,'s_metal','Y')
  attached(wallport,walls[0],(x,-73.8,21.95))
  end=ports[i][2].location.copy();start=wallport.location.copy()
  route(f'U{i+1} connected power cable',[start,(x,-74.4,21.95),(x+.4,-74.8,21.8),
        (x+.4,-75.25,21.8),(x,-75.55,21.95),end],.10,wallport,ports[i][2],'s_seal')

 # Transfer the rim's outboard load into the existing terminal, with fitted feet.
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 tower=bpy.data.objects['FORM03 / Raised shoulder terminal'];tree=acheck.tree(tower,dg)[0]
 for i,x in enumerate((-207.3,-193.5)):
  root=box(f'Terminal load foot {i+1}',(x,-84.1,26.10),(2.8,2.4,.60),'s_paint',.12)
  attached(root,replacements[HOSTS[1]],(x,-84.1,25.9))
  start=Vector((x,-84.2,26.25));aim=Vector((x,-110,33));direction=(aim-start).normalized()
  hit=tree.ray_cast(start,direction,40);assert hit[0] is not None,'Terminal support has no receiver'
  end=hit[0]+direction*.3
  support(f'Tapered terminal load web {i+1}',start,end,1.65,1.10,root,tower,'s_paint')
  # A narrower exposed cap emphasizes the web section without loose endpoints.
  webcap=s.beam(f'Terminal load web cap {i+1}',start,end,1.95,.24,'s_service')
  webcap['fore_kind']='structure'

 for name,d in CAMERAS.items():
  cam=base.camera(P+name,d['position'],d['target'],lens=d['lens']);cam.data.clip_end=100000000
 bpy.context.view_layer.update();assert protected()==before,'Original geometry/materials/lights/cameras changed'
 scene=bpy.context.scene;scene.name='KUHAI — Port Forward Shoulder Structure 08';scene['revision']='fore-structure-08'
 scene['fore08_input_sha256']=INPUT;scene['fore08_previous_objects']=json.dumps(REMOVED)
 scene.camera=bpy.data.objects[P+'fore08_context']
 a.output.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file
   p=a.output.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 report={'revision':'fore-structure-08','source_sha256':sha(a.output),'input_sha256':INPUT,
  'retained_previous_objects':REMOVED,'new_objects':len(bpy.data.collections[NEW].objects),'new_cameras':CAMERAS,
  'browser_tested':False,'published':False,'official_replica':False,'material_final':False}
 a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);build(p.parse_args())
