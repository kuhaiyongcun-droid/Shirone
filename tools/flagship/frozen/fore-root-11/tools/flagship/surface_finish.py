"""Side06 surface finish. Immutable repaired assembly; no geometry changes.

All procedural coordinates use world position so evaluated bake copies retain
the same appearance. Sparse wear is confined to handled removable skins.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f

P='SIDE06 / ';NEW='SIDE06_STRUCTURE';OLD='SIDE05_STRUCTURE'
INPUT='845cbc31ca00a14b0f0f9d2ce4a87e6e081a0f63fe9cf5697d9c2c3d93ff3892'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

PALETTE={
 's_paint':((.112,.143,.158),.025,.43,'coat'),
 's_service':((.052,.076,.085),.025,.41,'handled'),
 's_repair':((.156,.171,.166),.025,.48,'coat'),
 's_dark':((.021,.032,.037),.03,.58,'coat'),
 's_metal':((.34,.40,.415),.93,.285,'metal'),
 's_pipe':((.195,.25,.265),.88,.34,'metal'),
 's_seal':((.008,.013,.015),0,.82,'rubber'),
 's_mark':((.48,.205,.042),.01,.48,'coat'),
 's_label':((.49,.53,.495),.01,.54,'plain'),
 's_ivory':((.31,.315,.252),.02,.36,'coat'),
 's_connector':((.28,.205,.11),.9,.30,'metal'),
 's_primer':((.115,.132,.102),.02,.65,'plain'),
}

def material(key,values):
 color,metal,rough,finish=values
 m=bpy.data.materials.new(P+key);m.use_nodes=True;m.diffuse_color=(*color,1)
 n,l=m.node_tree.nodes,m.node_tree.links;b=n.get('Principled BSDF')
 b.inputs['Base Color'].default_value=(*color,1)
 b.inputs['Metallic'].default_value=metal;b.inputs['Roughness'].default_value=rough
 b.inputs['Coat Weight'].default_value=.10 if finish in ('coat','handled') else 0
 b.inputs['Coat Roughness'].default_value=.34
 m['finish_type']=finish;m['web_metallic']=metal;m['web_roughness']=rough
 g=n.new('ShaderNodeNewGeometry');g.name='World coordinates / stable through baking'
 macro=n.new('ShaderNodeTexNoise');macro.inputs['Scale'].default_value=.53;macro.inputs['Detail'].default_value=2
 l.new(g.outputs['Position'],macro.inputs['Vector'])
 ramp=n.new('ShaderNodeValToRGB');ramp.name='Quiet coating / 6 percent tonal range'
 ramp.color_ramp.elements[0].color=(*(c*.965 for c in color),1)
 ramp.color_ramp.elements[1].color=(*(c*1.025 for c in color),1)
 l.new(macro.outputs['Fac'],ramp.inputs['Fac']);l.new(ramp.outputs['Color'],b.inputs['Base Color'])
 roughmap=n.new('ShaderNodeMapRange');roughmap.name='Surface finish roughness'
 roughmap.inputs['To Min'].default_value=rough-.055;roughmap.inputs['To Max'].default_value=rough+.05
 l.new(macro.outputs['Fac'],roughmap.inputs['Value']);l.new(roughmap.outputs['Result'],b.inputs['Roughness'])
 micro=n.new('ShaderNodeTexNoise');micro.inputs['Scale'].default_value=42;micro.inputs['Detail'].default_value=2
 if finish=='metal':
  stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(1,1,.035)
  l.new(g.outputs['Position'],stretch.inputs[0]);l.new(stretch.outputs['Vector'],micro.inputs['Vector'])
 else:l.new(g.outputs['Position'],micro.inputs['Vector'])
 bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16 if finish=='metal' else .12
 bump.inputs['Distance'].default_value=.0012 if finish=='metal' else .0007
 l.new(micro.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
 if finish=='handled':
  edge=n.new('ShaderNodeMapRange');edge.name='Handled convex corners only'
  edge.inputs['From Min'].default_value=.54;edge.inputs['From Max'].default_value=.64
  l.new(g.outputs['Pointiness'],edge.inputs['Value'])
  broken=n.new('ShaderNodeMath');broken.operation='GREATER_THAN';broken.inputs[1].default_value=.61
  l.new(micro.outputs['Fac'],broken.inputs[0])
  mask=n.new('ShaderNodeMath');mask.operation='MULTIPLY';l.new(edge.outputs['Result'],mask.inputs[0]);l.new(broken.outputs[0],mask.inputs[1])
  mix=n.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[2].default_value=(.16,.175,.155,1)
  l.new(mask.outputs[0],mix.inputs[0]);l.new(ramp.outputs['Color'],mix.inputs[1]);l.new(mix.outputs[0],b.inputs['Base Color'])
 return m

def build(a):
 assert sha(a.source)==INPUT,'Repaired input fingerprint mismatch'
 assert not a.output.exists(),'Choose a fresh output'
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));f.PREFIX=P;before=f.protected()
 mats={k:material(k,v) for k,v in PALETTE.items()}
 lamp=bpy.data.materials['SIDE04 / warm service lamp'].copy();lamp.name=P+'warm service lamp';mats['warm service lamp']=lamp
 col=bpy.data.collections.new(NEW);bpy.context.scene.collection.children.link(col);mapping={}
 for old in list(bpy.data.collections[OLD].objects):
  o=old.copy();o.data=old.data.copy() if old.data else None;o.name=P+old.name.removeprefix('SIDE05 / ');col.objects.link(o);mapping[old.name]=o
  o['source_object']=old.name;o['revision']='side-surface-06'
  for slot in o.material_slots:
   if slot.material:
    key=slot.material.name.rsplit(' / ',1)[-1]
    if key not in mats:raise RuntimeError('Unhandled material '+key)
    slot.link='OBJECT';slot.material=mats[key]
  name=o.name.removeprefix(P)
  if name.startswith(('Replaceable electronics module','Cassette lid overlap','Canister removable end cap','Shield two-piece lid / fixed','Removable equipment shield')):
   o.material_slots[0].link='OBJECT';o.material_slots[0].material=mats['s_service']
  if name.startswith(('Cassette connected cable','Junction hull cable')):
   o.material_slots[0].link='OBJECT';o.material_slots[0].material=mats['s_seal']
  if name.startswith(('Carrier transverse shoe','Equipment rear support','Supply manifold wall support','Return manifold wall support','Cassette wall support')):
   o.material_slots[0].link='OBJECT';o.material_slots[0].material=mats['s_service']
 for o in mapping.values():
  for k in ('start_target','end_target','mate_manifold'):
   if o.get(k) in mapping:o[k]=mapping[o[k]].name
  for mod in o.modifiers:
   if mod.type=='BOOLEAN' and mod.object and mod.object.name in mapping:mod.object=mapping[mod.object.name]
 bpy.data.collections[OLD].hide_render=True;bpy.data.collections[OLD].hide_viewport=True
 bpy.context.view_layer.update();assert f.protected()==before,'Prior content changed'
 a.output.parent.mkdir(parents=True,exist_ok=True)
 for img in bpy.data.images:
  if img.type=='IMAGE' and img.users:
   assert img.packed_file,'Unpacked source image'
   p=a.output.parent/'textures'/Path(img.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(img.packed_file.data)
   img.filepath='//textures/'+p.name
   for packed in img.packed_files:packed.filepath=img.filepath
 scene=bpy.context.scene;scene.name='KUHAI — Service Surface 06';scene['revision']='side-surface-06'
 bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 report={'revision':'side-surface-06','input_sha256':INPUT,'source_sha256':sha(a.output),'geometry_changes':False,
         'palette':PALETTE,'objects':len(col.objects),'browser_tested':False,'published':False}
 a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);build(p.parse_args())
