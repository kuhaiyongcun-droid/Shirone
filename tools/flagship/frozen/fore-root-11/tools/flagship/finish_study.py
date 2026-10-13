"""Side finish study 04. Clone recovered side03; preserve every prior datablock.

No source overwrite, network calls or GPU use. Metric source units.
Recovered side03 must first pass side_study.inspect and be registered in
finish-study-04.json. The original historical side03 file is NOT claimed recovered.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import side_study as s
import build_scene as base
from form_study import contract, digest, object_record
from home_look import node_record
from integration_study import archive_fingerprint

NEW = 'SIDE04_STRUCTURE'
PREFIX = 'SIDE04 / '
CONFIG_PATH = ROOT / 'finish-study-04.json'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def protected():
    names = sorted(o.name for o in bpy.data.objects if not o.name.startswith(PREFIX))
    return {'objects': s.protected(names), 'archive': archive_fingerprint(),
            'lighting': contract(),
            'materials': {m.name: digest(node_record(m)) for m in bpy.data.materials
                          if not m.name.startswith(PREFIX)},
            'cameras': {o.name: digest(object_record(o)) for o in bpy.data.objects if o.type == 'CAMERA'}}


def physical_finish(old, color, metallic, roughness):
    mat = old.copy()
    mat.name = PREFIX + old.name.removeprefix('SIDE03 / ')
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    for socket in (bsdf.inputs['Base Color'], bsdf.inputs['Metallic'], bsdf.inputs['Roughness'], bsdf.inputs['Normal']):
        for link in list(socket.links):
            links.remove(link)
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Coat Weight'].default_value = .06 if metallic < .3 else 0
    bsdf.inputs['Coat Roughness'].default_value = .38
    tex = nodes.new('ShaderNodeTexCoord')
    macro = nodes.new('ShaderNodeTexNoise')
    macro.name = 'Meter scale coating variation'
    macro.inputs['Scale'].default_value = 1.15
    macro.inputs['Detail'].default_value = 2
    links.new(tex.outputs['Object'], macro.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*(c*.92 for c in color), 1)
    ramp.color_ramp.elements[1].color = (*(c*1.06 for c in color), 1)
    links.new(macro.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.name = 'Finish roughness range'
    rough.inputs['To Min'].default_value = max(.08, roughness-.035)
    rough.inputs['To Max'].default_value = min(.9, roughness+.045)
    links.new(macro.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    micro = nodes.new('ShaderNodeTexNoise')
    micro.name = 'Fine finish / no exaggerated displacement'
    micro.inputs['Scale'].default_value = 65
    micro.inputs['Detail'].default_value = 2
    links.new(tex.outputs['Object'], micro.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .12
    bump.inputs['Distance'].default_value = .0015
    links.new(micro.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    mat.diffuse_color = (*color, 1)
    mat['finish_metallic'], mat['finish_roughness'] = metallic, roughness
    return mat


def materials():
    palette = {
        's_paint': ((.088, .119, .145), .04, .46),
        's_repair': ((.15, .168, .17), .04, .51),
        's_dark': ((.029, .039, .047), .13, .6),
        's_metal': ((.3, .36, .39), .86, .3),
        's_pipe': ((.11, .15, .17), .69, .37),
        's_seal': ((.01, .014, .017), 0, .78),
        's_mark': ((.48, .225, .061), .04, .51),
        's_label': ((.48, .54, .52), .02, .53),
    }
    mapping = {}
    for key, (color, metal, rough) in palette.items():
        old = bpy.data.materials['SIDE03 / ' + key]
        mat = physical_finish(old, color, metal, rough)
        base.MATERIALS[key] = mat
        mapping[old.name] = mat
    for key, color, metal, rough in [
        ('s_ivory', (.255,.275,.26), .04,.43),
        ('s_oxide', (.115,.075,.048), .12,.58),
        ('s_connector', (.235,.18,.102), .78,.34),
        ('s_primer', (.14,.16,.155), .05,.58),
    ]:
        mat = base.material(PREFIX + key, color, metal, rough)
        base.MATERIALS[key] = mat
    lamp = bpy.data.materials['SIDE03 / warm service lamp'].copy()
    lamp.name = PREFIX + 'warm service lamp'
    base.MATERIALS['s_lamp'] = lamp
    mapping['SIDE03 / warm service lamp'] = lamp
    return mapping


def cylinder(name, loc, radius, depth, mat='s_metal', axis='Z', vertices=32):
    return s.finish(base.cylinder(name, loc, radius, depth, mat, axis, NEW, vertices=vertices),
                    'mechanical coupling with actual volume')


def label(text, loc, size=.26, mat='s_label'):
    bpy.ops.object.select_all(action='DESELECT')
    curve = bpy.data.curves.new(PREFIX+'stencil '+text, 'FONT')
    curve.body, curve.size, curve.extrude = text, size, .001
    curve.align_x = 'LEFT'
    o = bpy.data.objects.new(PREFIX+'stencil '+text, curve)
    bpy.data.collections[NEW].objects.link(o)
    o.location = loc
    o.rotation_euler[0] = math.pi/2
    o.data.materials.append(base.MATERIALS[mat])
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.object
    o.select_set(False)
    o['role'], o['function'] = 'hull', 'small equipment identity stencil; source meters'
    o['validation_type'] = 'surface_marking'
    return o


def additions():
    # Nested removable lids, retaining rims and actual pull handles.
    for i,x in enumerate((-185.5,-182.1,-178.7)):
        z=33.1+i*.12
        for dx in (-1.045,1.045):
            s.box('Cassette lid overlap',(x+dx,-24.91,z+.12),(.13,.22,3.62),'s_paint',.018)
        for dz in (-1.64,1.87):
            s.box('Cassette lid overlap',(x,-24.91,z+dz),(2.18,.22,.12),'s_paint',.018)
        for dx in (-.64,.64):
            s.pipe('Recessed lifting handle',[(x+dx-.18,-25.02,z+.95),(x+dx-.18,-25.25,z+.95),
                (x+dx+.18,-25.25,z+.95),(x+dx+.18,-25.02,z+.95)],.042,'s_metal')
        s.box('Cassette removable header',(x,-25.00,z+1.47),(1.62,.1,.44),'s_ivory',.025)
        label('E-0'+str(i+1),(x-.69,-25.058,z+1.34),.25,'s_dark')
        for dx in (-.78,.78):
            s.box('Captive quarter-turn latch',(x+dx,-25.06,z-1.42),(.13,.12,.28),'s_metal',.02)
        # Retained thermal ribs meet side plates; protective cover closes around the unit.
        for j in range(3):
            s.box('Cassette side cooling plate',(x-1.22,-23.65,z-.7+j*.60),(.10,1.6,.16),'s_dark',.025)
        cylinder('Cassette sealed plug',(x+.45,-24.0,z-2.0),.21,.35,'s_connector')
        s.box('Isolated equipment foot',(x,-23.0,z-2.30),(2.48,1.90,.22),'s_seal',.04)
        # Local worn tracks from extracting a cassette, intentionally sparse.
        for dx in (-.96,.96):
            s.box('Cassette extraction contact track',(x+dx,-24.17,z-2.41),(.06,.8,.025),'s_metal',.006)

    # Equipment mount frame, edge shoes and split cylindrical shell caps.
    for i,x in enumerate((-169.6,-163.9,-158.8)):
        y=s.surface_y(x)+2.1
        z=33.8 if i<2 else 31.8
        for dz in (-2.02,2.02):
            cylinder('Canister removable end cap',(x,y,z+dz),.91,.20,'s_paint')
            cylinder('Canister compression flange',(x,y,z+dz*.94),.92,.055,'s_metal')
        cylinder('Canister bottom coupling',(x,y,z-2.25),.27,.33,'s_connector')
        cylinder('Canister top coupling',(x,y,z+2.32),.34,.43,'s_connector')
        cylinder('Canister top locking nut',(x,y,z+2.44),.39,.16,'s_metal',vertices=6)
        # Front instruments are grouped onto one small service plate, not random greebles.
        s.box('Canister instrument saddle',(x,y-.825,z+.44),(.90,.23,1.0),'s_ivory',.07)
        cylinder('Recessed diagnostic port',(x,y-.970,z+.59),.23,.08,'s_dark','Y')
        cylinder('Diagnostic port inset',(x,y-1.016,z+.59),.13,.025,'s_pipe','Y')
        label('P'+str(i+1),(x-.30,y-.955,z+.03),.23,'s_dark')
        for dx in (-1.50,1.50):
            s.box('Carrier side folded flange',(x+dx,y+.52,z),(.16,.24,5.8),'s_paint',.025)
        for dz in (-2.60,2.60):
            s.box('Carrier transverse shoe',(x,y+.47,z+dz),(3.30,.35,.28),'s_pipe',.035)
        for dz in (-1.8,1.8):
            for dx in (-1.0,1.0):
                cylinder('Split clamp axial pin',(x+dx,y-.99,z+dz),.12,.18,'s_metal','Y',vertices=6)
        # First unit's painted body reads separately from fittings and dark isolators.
        if i==0:
            s.box('Maintenance replacement tab',(x+.98,y-.12,z+1.80),(.20,.7,.06),'s_mark',.009)

    # Long controlled service tray follows the structural sill. Two lanes terminate at trunk.
    a=(-188,-28.65,29.45);b=(-153.5,-19.55,25.45)
    s.beam('Sill inner folded channel',a,b,.20,.48,'s_paint','continuous folded service channel')
    for x in (-186,-182,-178,-174,-170,-166,-162,-158):
        z=29.45+(x+188)*(25.45-29.45)/34.5
        y=s.surface_y(x)+.5
        s.box('Tray spaced transverse support',(x,y,z),(.15,1.15,.24),'s_pipe',.025)
    s.pipe('Separated signal umbilical',[(-176.3,-22.45,29.3),(-175,-22.45,28.65),
        (-169,-21.2,28.1),(-161,-19.0,27.35),(-153.6,-17.4,27.35)],.075,'s_dark')
    for x,y,z in ((-171.5,-21.7,28.35),(-165.8,-20.45,27.83),(-160.0,-18.75,27.35)):
        s.box('Cable tray cushioned cleat',(x,y,z),(.20,.42,.37),'s_paint',.024)
    s.box('Trunk removable terminal cover',(-153.6,-18.6,28.2),(1.40,.14,1.03),'s_ivory',.055)
    label('J-07',(-154.13,-18.68,28.12),.22,'s_dark')

    # A shallow layered lid on the existing debris shield stays attached to its supports.
    perimeter=[(-171.84,34.15),(-166.26,33.69),(-166.26,34.93),(-171.84,35.40)]
    s.xz_prism('Shield compressed gasket',perimeter,-28.345,-28.31,'s_seal',.014,'sealed removable panel boundary')
    left=[(-171.68,34.29),(-169.2,34.09),(-169.2,35.03),(-171.68,35.24)]
    right=[(-169.10,34.08),(-166.43,33.86),(-166.43,34.77),(-169.10,35.00)]
    s.xz_prism('Shield two-piece lid / fixed',left,-28.405,-28.35,'s_paint',.023,'folded fixed guard skin')
    s.xz_prism('Shield two-piece lid / replaceable',right,-28.415,-28.35,'s_repair',.023,'replaceable access cover')
    label('SVC 07',(-170.9,-28.43,34.55),.28,'s_label')
    for x,z in ((-171.4,34.70),(-166.65,34.30)):
        s.box('Recessed guard latch',(x,-28.46,z),(.12,.10,.28),'s_dark',.025)
        s.box('Latch actuating slot',(x,-28.516,z),(.035,.016,.15),'s_metal',.004)
    # Human-scale fold-out grips are bolted to the guard, with both endpoints attached.
    for x in (-170.25,-167.75):
        z=34.03+(x+169.2)*(-.083)
        s.pipe('Folded maintenance grip',[(x-.22,-28.42,z),(x-.22,-28.72,z-.06),
            (x+.22,-28.72,z-.06),(x+.22,-28.42,z)],.036,'s_metal')
    # Deliberate short contact marks where the removable shield lid is handled.
    for x,width in ((-171.1,.39),(-169.6,.29),(-167.2,.35)):
        z=35.40-(x+171.84)*.083
        s.box('Lid tool contact / primer',(x,-28.433,z-.085),(width,.012,.034),'s_primer',.004)
        s.box('Lid tool contact / bare edge',(x+.04,-28.444,z-.081),(width*.40,.009,.015),'s_metal',.002)
    # Rear rack ribs and terminal plates explain how loads and services reach the wall.
    for x,z in ((-171.9,37.8),(-166.8,37.8),(-161.4,35.8)):
        s.box('Rear equipment mounting rail',(x,-16.7,z-3.0),(.17,.32,7.4),'s_pipe',.028)
        s.box('Rail header terminal',(x,-17.0,z+.40),(.7,.30,.72),'s_dark',.06)
    for x in (-169.6,-163.9,-158.8):
        y=s.surface_y(x)+2.1
        z=33.8 if x<-160 else 31.8
        cylinder('Upper line isolated union',(x,y+.35,z+3.50),.265,.36,'s_paint')


def build(source,output):
    cfg=json.loads(CONFIG_PATH.read_text())
    if sha(source)!=cfg['recovered_input_sha256']:
        raise RuntimeError('Unregistered recovered input')
    if output.exists():
        raise RuntimeError('Output exists; select a new revision')
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    before=protected()
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    base.collection(NEW)
    palette=materials()
    mapping={}
    for old in list(bpy.data.collections['SIDE03_STRUCTURE'].objects):
        o=old.copy()
        if old.data:o.data=old.data.copy()
        o.name=PREFIX+old.name.removeprefix('SIDE03 / ')
        bpy.data.collections[NEW].objects.link(o)
        o['source_object']=old.name
        mapping[old.name]=o
        for slot in o.material_slots:
            if slot.material and slot.material.name in palette:
                target_material=palette[slot.material.name]
                slot.link='OBJECT';slot.material=target_material
        # Reduce oversized local fasteners while keeping load pads substantial.
        if 'Captive hex fixing' in o.name:
            o.scale*=.68
        if 'Vertical service cylinder' in o.name:
            o.material_slots[0].link='OBJECT';o.material_slots[0].material=base.MATERIALS['s_ivory']
        if 'Structural attachment pad' in o.name:
            for mod in o.modifiers:
                if mod.type=='BEVEL':mod.width=.055
        if 'Opened structural abutment' in o.name:
            o.material_slots[0].link='OBJECT';o.material_slots[0].material=base.MATERIALS['s_paint']
    # Remap any self references only; original hidden boolean cutter collection is retained.
    for o in mapping.values():
        for mod in o.modifiers:
            if mod.type=='BOOLEAN' and mod.object and mod.object.name in mapping:
                mod.object=mapping[mod.object.name]
    bpy.data.collections['SIDE03_STRUCTURE'].hide_render=True
    bpy.data.collections['SIDE03_STRUCTURE'].hide_viewport=True
    s.NEW,s.PREFIX=NEW,PREFIX
    s.PARTS=[]
    bpy.ops.object.select_all(action='DESELECT')
    additions()
    bpy.context.view_layer.update()
    assert protected()==before,'Prior objects, material nodes, archive, lighting or cameras changed'
    scene=bpy.context.scene
    scene.name='KUHAI — Port Service Finish 04'
    scene['revision']='side-finish-04'
    scene['recovery_note']='Rebuilt side03 from verified home-look-01 and pinned GitHub generator; historical side03 bytes unavailable'
    scene.camera=bpy.data.objects['side03_context']
    output.parent.mkdir(parents=True,exist_ok=True)
    for img in bpy.data.images:
        if img.type=='IMAGE' and img.users:
            if not img.packed_file:raise RuntimeError('Missing packed texture')
            p=output.parent/'textures'/Path(img.filepath).name
            p.parent.mkdir(exist_ok=True);p.write_bytes(img.packed_file.data)
            img.filepath='//textures/'+p.name
            for packed in img.packed_files:packed.filepath=img.filepath
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(output.resolve()),compress=True,relative_remap=False)
    report={'revision':'side-finish-04','source_sha256':sha(output),'recovered_input_sha256':sha(source),
            'new_collection_objects':len(bpy.data.collections[NEW].objects),
            'previous_content_preserved':True,'browser_tested':False,'blender':bpy.app.version_string}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


def inspect(source,scene,output):
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()));before=protected()
    bpy.ops.wm.open_mainfile(filepath=str(scene.resolve()));after=protected()
    rows=[]
    bpy.data.collections[NEW].hide_viewport=False
    bpy.context.view_layer.update()
    dg=bpy.context.evaluated_depsgraph_get()
    for o in bpy.data.collections[NEW].objects:
        if o.type!='MESH':continue
        e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
        bm=bmesh.new();bm.from_mesh(m)
        marking=o.get('validation_type')=='surface_marking'
        closed=bool(bm.faces) and all(edge.is_manifold for edge in bm.edges) and bm.calc_volume(signed=True)>0
        rows.append({'name':o.name,'triangles':len(m.loop_triangles),'closed':closed,'surface_marking':marking})
        bm.free();e.to_mesh_clear()
    images=[{'name':i.name,'packed':bool(i.packed_file),'relative':i.filepath.startswith('//'),
             'exists':Path(bpy.path.abspath(i.filepath)).exists()} for i in bpy.data.images if i.type=='IMAGE' and i.users]
    checks={'protected_content':before==after,'closed_new_solids':all(r['closed'] or r['surface_marking'] for r in rows),
            'portable_images':all(i['packed'] and i['relative'] and i['exists'] for i in images),
            'previous_hidden':bpy.data.collections['SIDE03_STRUCTURE'].hide_render,
            'current_visible':not bpy.data.collections[NEW].hide_render}
    report={'checks':checks,'passed':all(checks.values()),'source_sha256':sha(scene),'meshes':rows,'images':images,'browser_tested':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'checks':checks,'invalid':[r['name'] for r in rows if not r['closed'] and not r['surface_marking']]}),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['build','inspect'])
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scene',type=Path)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.command=='build':build(args.source,args.output)
    else:inspect(args.source,args.scene,args.output)
