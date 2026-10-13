"""Fore09 material-only copy of the immutable, repaired fore08 shoulder.

No geometry, transform, camera, light or original material edits. Wear follows
removable lid margins, quarter-turn pins and lifting-handle feet; broad armor
stays quiet. Printed labels are original project artwork, not an external asset.
"""
import argparse,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f
import surface_finish as sf
from fore_check import require as fore_require
from surface_finish import sha

P='FORE09 / ';NEW='FORE09_STRUCTURE';OLD='FORE08_STRUCTURE';OLDP='FORE08 / '
INPUT='c0df9ec63433548bd751438c71b9f237c2de7445248d1e691589153875b3f405'
PALETTE={
 'armor':((.106,.14,.161),.025,.43,'coat'),
 'casing':((.045,.067,.079),.025,.39,'coat'),
 'liner':((.033,.05,.056),.025,.57,'coat'),
 'lid1':((.08,.114,.126),.025,.34,'coat'),
 'lid2':((.175,.195,.174),.025,.47,'coat'),
 'bed':((.018,.029,.034),.025,.64,'coat'),
 'metal':((.33,.38,.40),.95,.26,'metal'),
 'union':((.30,.267,.205),.91,.30,'metal'),
 'pipe':((.19,.25,.275),.92,.32,'metal'),
 'rubber':((.007,.011,.014),0,.81,'rubber'),
 'cable':((.012,.019,.024),0,.67,'rubber'),
 'mark':((.42,.17,.027),.01,.48,'coat'),
 'label':((.017,.027,.033),.01,.49,'plain'),
}

def scalar(n,l,op,a,b=None,label=None):
 node=n.new('ShaderNodeMath');node.operation=op
 if label:node.label=label;node.name=label
 for i,value in enumerate((a,b)):
  if value is None:continue
  if hasattr(value,'bl_idname'):l.new(value,node.inputs[i])
  else:node.inputs[i].default_value=value
 return node.outputs[0]

def lid_details(m,x,unit,texture):
 n,l=m.node_tree.nodes,m.node_tree.links;b=n.get('Principled BSDF')
 g=n.get('World coordinates / stable through baking')
 sep=n.new('ShaderNodeSeparateXYZ');l.new(g.outputs['Position'],sep.inputs[0])
 def offset(axis,value):return scalar(n,l,'SUBTRACT',sep.outputs[axis],value)
 def circle(px,py,inner,outer):
  dx=offset('X',px);dy=offset('Y',py)
  rr=scalar(n,l,'ADD',scalar(n,l,'MULTIPLY',dx,dx),scalar(n,l,'MULTIPLY',dy,dy))
  return scalar(n,l,'MULTIPLY',scalar(n,l,'GREATER_THAN',rr,inner*inner),scalar(n,l,'LESS_THAN',rr,outer*outer))
 # Only the actual margins on the top skin, without coating all convex edges.
 dx=scalar(n,l,'ABSOLUTE',offset('X',x));dy=scalar(n,l,'ABSOLUTE',offset('Y',-78.2))
 ex=scalar(n,l,'MULTIPLY',scalar(n,l,'GREATER_THAN',dx,2.47),scalar(n,l,'LESS_THAN',dy,1.08))
 ey=scalar(n,l,'MULTIPLY',scalar(n,l,'GREATER_THAN',dy,1.37),scalar(n,l,'LESS_THAN',dx,2.18))
 mask=scalar(n,l,'MAXIMUM',ex,ey)
 for px in (x-2.1,x+2.1):
  for py in (-79.65,-76.75):mask=scalar(n,l,'MAXIMUM',mask,circle(px,py,.15,.24))
 for h in (-1.55,1.55):
  for foot in (-.32,.32):mask=scalar(n,l,'MAXIMUM',mask,circle(x+h+foot,-78.2,.055,.13))
 top=scalar(n,l,'GREATER_THAN',sep.outputs['Z'],24.06)
 mask=scalar(n,l,'MULTIPLY',mask,top)
 noise=n.new('ShaderNodeTexNoise');noise.name='Broken wear at documented service contacts';noise.inputs['Scale'].default_value=33;noise.inputs['Detail'].default_value=2
 l.new(g.outputs['Position'],noise.inputs['Vector'])
 mask=scalar(n,l,'MULTIPLY',mask,scalar(n,l,'GREATER_THAN',noise.outputs['Fac'],.57),'Sparse primer exposure / service contacts only')
 mix=n.new('ShaderNodeMixRGB');mix.name='Local primer beneath removed coating';mix.inputs[2].default_value=(.115,.13,.105,1)
 l.new(b.inputs['Base Color'].links[0].from_socket,mix.inputs[1]);l.new(mask,mix.inputs[0]);l.new(mix.outputs[0],b.inputs['Base Color'])
 rough=n.new('ShaderNodeMixRGB');rough.inputs[2].default_value=(.62,.62,.62,1)
 l.new(b.inputs['Roughness'].links[0].from_socket,rough.inputs[1]);l.new(mask,rough.inputs[0]);l.new(rough.outputs[0],b.inputs['Roughness'])
 # Coordinate-locked print remains stable when objects are merged for web baking.
 uv=n.new('ShaderNodeCombineXYZ')
 l.new(scalar(n,l,'DIVIDE',offset('X',x-2.6),5.2),uv.inputs['X'])
 l.new(scalar(n,l,'DIVIDE',offset('Y',-79.7),3.0),uv.inputs['Y'])
 img=bpy.data.images.load(str(texture.resolve()),check_existing=True);img.pack();img.colorspace_settings.name='Non-Color'
 tex=n.new('ShaderNodeTexImage');tex.name='Original maintenance print / PCU '+str(unit);tex.image=img;tex.extension='CLIP';l.new(uv.outputs[0],tex.inputs['Vector'])
 printmask=scalar(n,l,'MULTIPLY',tex.outputs['Color'],top)
 ink=n.new('ShaderNodeMixRGB');ink.name='Maintenance stencil / matte ink';ink.inputs[2].default_value=(.56,.59,.55,1)
 l.new(printmask,ink.inputs[0]);l.new(mix.outputs[0],ink.inputs[1]);l.new(ink.outputs[0],b.inputs['Base Color'])
 m['wear_locations']='lid margins; quarter-turn fasteners; lifting-handle feet';m['print_unit']=unit

def build(a):
 assert sha(a.source)==INPUT,'Immutable fore08 fingerprint mismatch';fore_require(a.source,a.validation)
 assert not a.output.exists(),'Choose a fresh output file'
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));f.PREFIX=P;before=f.protected()
 sf.P=P;mats={k:sf.material(k,v) for k,v in PALETTE.items()}
 for unit,x in ((1,-205.8),(2,-195.4)):lid_details(mats['lid'+str(unit)],x,unit,a.prints/f'fore09-panel-{unit}-print.png')
 col=bpy.data.collections.new(NEW);bpy.context.scene.collection.children.link(col);mapping={}
 hostmats={}
 for old in list(bpy.data.collections[OLD].objects):
  o=old.copy();o.data=old.data.copy();o.name=P+old.name.removeprefix(OLDP);col.objects.link(o);mapping[old.name]=o
  o['revision']='fore-surface-09';o['fore09_source_object']=old.name
  name=o.name.removeprefix(P)
  if o.get('fore_kind')=='host':
   # Broad existing armor keeps the original art direction exactly.
   for slot in o.material_slots:
    mat=slot.material
    if mat.name not in hostmats:hostmats[mat.name]=mat.copy();hostmats[mat.name].name=P+'retained '+mat.name
    slot.link='OBJECT';slot.material=hostmats[mat.name]
   continue
  key='armor'
  if 'conditioning casing' in name or 'cooling rib' in name or 'bolted support' in name:key='casing'
  elif 'continuous sill' in name or 'bulkhead' in name.lower() or 'web cap' in name:key='liner'
  if name=='Sealed channel bed':key='bed'
  if 'removable top panel' in name:key='lid1' if 'U1 ' in name else 'lid2'
  if 'gasket' in name or 'power gland' in name:key='rubber'
  if 'power cable' in name:key='cable'
  if 'recessed status plate' in name:key='label'
  if 'identity stripe' in name:key='mark'
  if any(t in name for t in ('locking pin','quarter-turn pin','lifting handle','wall power socket','bulkhead sleeve')):key='metal'
  if 'fluid flange' in name:key='casing'
  if 'fluid union' in name:key='union'
  if 'coolant link' in name:key='pipe'
  for slot in o.material_slots:slot.link='OBJECT';slot.material=mats[key]
 for o in mapping.values():
  for key in ('fore_start_target','fore_end_target','fore_attachment_target'):
   if o.get(key) in mapping:o[key]=mapping[o[key]].name
  for mod in o.modifiers:
   if mod.type=='BOOLEAN' and mod.object and mod.object.name in mapping:mod.object=mapping[mod.object.name]
 bpy.data.collections[OLD].hide_render=True;bpy.data.collections[OLD].hide_viewport=True
 bpy.context.view_layer.update();assert f.protected()==before,'Prior content changed'
 a.output.parent.mkdir(parents=True,exist_ok=True)
 for img in bpy.data.images:
  if img.type=='IMAGE' and img.users:
   assert img.packed_file,'Unpacked source image';p=a.output.parent/'textures'/Path(img.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(img.packed_file.data)
   img.filepath='//textures/'+p.name
   for packed in img.packed_files:packed.filepath=img.filepath
 scene=bpy.context.scene;scene.name='KUHAI — Forward Shoulder Surface 09';scene['revision']='fore-surface-09';scene['fore09_input_sha256']=INPUT
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 r={'revision':'fore-surface-09','source_sha256':sha(a.output),'input_sha256':INPUT,'objects':len(col.objects),'geometry_changes':False,'palette':PALETTE,'browser_tested':False,'published':False}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--prints',type=Path,required=True);p.add_argument('--output',type=Path,required=True);build(p.parse_args())
