"""Add reversible side armor and a procedural coating sample to bridge-study-01.

Original ship objects and shaders remain unchanged. The painted inspection
cover is the actual object used by bake_bridge_finish.py, not a substitute plane.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_scene as base
from bridge_study import fingerprint, sha
from form_study import contract, digest, object_record
from integration_study import MATERIAL_MAP, archive_fingerprint
from render_study import peak_process_rss_mib, select_device
from surface_layout import inset

CONFIG=json.loads((ROOT/"bridge-study-02.json").read_text())
GROUP="BRIDGE02_DETAILS"
PREFIX="BRIDGE02 / "
COVER=PREFIX+"Port inspection cover"


def shader(name,poly,worn=True):
    """Distance-to-edge coating mask in physical object coordinates.

    Paint is dielectric, primer is matte, and exposed alloy is metallic. The
    chipped region is interrupted by noise, not a uniform bright outline.
    """
    mat=base.material(name,(.052,.069,.071),0,CONFIG["paint_roughness"])
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    bsdf=nodes.get("Principled BSDF")
    def operation(op,a,b):
        n=nodes.new("ShaderNodeMath");n.operation=op
        for i,value in enumerate((a,b)):
            if isinstance(value,(float,int)):n.inputs[i].default_value=value
            else:links.new(value,n.inputs[i])
        return n.outputs[0]
    coord=nodes.new("ShaderNodeTexCoord")
    xyz=nodes.new("ShaderNodeSeparateXYZ");links.new(coord.outputs["Object"],xyz.inputs[0])
    distance=None
    for a,b in zip(poly,poly[1:]+poly[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        x=operation("SUBTRACT",xyz.outputs["X"],a[0])
        y=operation("SUBTRACT",xyz.outputs["Y"],a[1])
        cross=operation("SUBTRACT",operation("MULTIPLY",y,dx/length),operation("MULTIPLY",x,dy/length))
        distance=cross if distance is None else operation("MINIMUM",distance,cross)
    noise=nodes.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=9
    noise.inputs["Detail"].default_value=2
    links.new(coord.outputs["Object"],noise.inputs["Vector"])
    threshold=operation("SUBTRACT",operation("MULTIPLY",noise.outputs["Fac"],CONFIG["edge_chip_reach_m"]),.048)
    metal=operation("LESS_THAN",distance,threshold)
    primer=operation("LESS_THAN",distance,operation("ADD",threshold,CONFIG["primer_margin_m"]))
    if not worn:
        metal=operation("MULTIPLY",metal,0)
        primer=operation("MULTIPLY",primer,0)
    macro=nodes.new("ShaderNodeTexNoise");macro.inputs["Scale"].default_value=.44
    macro.inputs["Detail"].default_value=2
    links.new(coord.outputs["Object"],macro.inputs["Vector"])
    tint=nodes.new("ShaderNodeValToRGB")
    tint.color_ramp.elements[0].color=(.049,.065,.067,1)
    tint.color_ramp.elements[1].color=(.057,.075,.077,1)
    links.new(macro.outputs["Fac"],tint.inputs["Fac"])
    under=nodes.new("ShaderNodeMixRGB")
    links.new(primer,under.inputs[0]);links.new(tint.outputs["Color"],under.inputs[1])
    under.inputs[2].default_value=(.084,.065,.043,1)
    mix=nodes.new("ShaderNodeMixRGB")
    links.new(metal,mix.inputs[0]);links.new(under.outputs[0],mix.inputs[1])
    mix.inputs[2].default_value=(.21,.235,.24,1)
    links.new(mix.outputs[0],bsdf.inputs["Base Color"])
    links.new(metal,bsdf.inputs["Metallic"])
    scale=nodes.new("ShaderNodeVectorMath");scale.operation="SCALE";scale.inputs[3].default_value=.4
    links.new(coord.outputs["Object"],scale.inputs[0])
    texture=nodes.new("ShaderNodeTexImage")
    texture.image=bpy.data.images["Blue Metal Plate roughness 1024 - CC0"]
    texture.projection="BOX";texture.projection_blend=.15
    links.new(scale.outputs[0],texture.inputs["Vector"])
    variance=operation("MULTIPLY",operation("SUBTRACT",texture.outputs["Color"],.5),.12)
    rough=operation("ADD",variance,CONFIG["paint_roughness"])
    rough=operation("ADD",operation("MULTIPLY",rough,operation("SUBTRACT",1,metal)),
                    operation("MULTIPLY",metal,CONFIG["metal_roughness"]))
    links.new(rough,bsdf.inputs["Roughness"])
    grain=nodes.new("ShaderNodeTexNoise");grain.inputs["Scale"].default_value=70
    grain.inputs["Detail"].default_value=2
    links.new(coord.outputs["Object"],grain.inputs["Vector"])
    height=operation("SUBTRACT",operation("MULTIPLY",grain.outputs["Fac"],.24),metal)
    bump=nodes.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.4
    bump.inputs["Distance"].default_value=CONFIG["micro_height_m"]
    links.new(height,bump.inputs["Height"]);links.new(bump.outputs["Normal"],bsdf.inputs["Normal"])
    mat["edge_mask"]="Signed distance to convex perimeter; irregular chips in scene meters"
    mat["metallic_rule"]="Paint and primer 0; exposed alloy 1"
    return mat


def frame(normal,origin):
    v=Vector((0,0,1))
    u=v.cross(normal).normalized()
    return Matrix(((u.x,v.x,normal.x,origin.x),(u.y,v.y,normal.y,origin.y),
                   (u.z,v.z,normal.z,origin.z),(0,0,0,1)))


def outline(width,height,corner):
    x,y=width/2,height/2;c=corner
    return [(-x+c,-y),(x-c,-y),(x,-y+c),(x,y-c),(x-c,y),(-x+c,y),(-x,y-c),(-x,-y+c)]


def plate(name,poly,depth,matrix,material,edge=.04):
    # Every authored part uses its own local frame, also fixing shader scale.
    obj=base.prism(PREFIX+name,poly,0,depth,material,GROUP,edge)
    obj.matrix_world=matrix
    obj["role"],obj["revision"]="hull",CONFIG["revision"]
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
    return obj


def fitting(name,xy,dims,normal,origin,material="dark",edge=.025):
    center=origin+frame(normal,origin).to_3x3()@Vector(xy)
    return plate(name,outline(dims[0],dims[1],min(dims[0],dims[1])*.12),dims[2],
                 frame(normal,center),material,edge)


def geometry():
    host=bpy.data.objects["FORM03 / Dorsal command crest"]
    for face in host.data.polygons:
        if abs(face.normal.y)<.9 or not -175<face.center.x<-129:continue
        normal=face.normal.copy()
        points=[host.matrix_world@host.data.vertices[i].co for i in face.vertices]
        points=inset(points,normal,CONFIG["side_panel_inset_m"])
        center=sum(points,Vector())/len(points)
        matrix=frame(normal,center+normal*CONFIG["side_panel_lift_m"])
        inverse=matrix.inverted()
        poly=[tuple((inverse@p)[:2]) for p in points]
        if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))<0:poly.reverse()
        label=("Port" if normal.y<0 else "Starboard")+f" crest armor {face.index:02d}"
        key="finish_"+str(face.index)
        base.MATERIALS[key]=shader("BRIDGE02_paint_"+str(face.index),poly)
        obj=plate(label,poly,CONFIG["side_panel_thickness_m"],matrix,key,.07)
        obj["host_object"]=host.name;obj["host_face"]=face.index

    for side in (-1,1):
        normal=Vector((.21693046,side*.9761871,0)).normalized()
        center=Vector((-155,side*14,49.4))
        fitting("Inspection gasket",(0,0,.58),(5.15,3.85,.15),normal,center)
        shape=outline(4.8,3.5,.25)
        key="cover_paint_"+str(side)
        base.MATERIALS[key]=shader("BRIDGE02_inspection_coating_"+str(side),shape)
        obj=plate("Port inspection cover" if side==-1 else "Starboard inspection cover",
                  shape,.24,frame(normal,center+normal*.77),key,.055)
        obj["material_sample"]=side==-1
        # Small pockets and captive alloy fasteners, restrained to service points.
        for x in (-1.95,1.95):
            for y in (-1.27,1.27):
                fitting("Captive fixing pocket",(x,y,1.012),(.38,.36,.035),normal,center,"dark",.024)
                fitting("Captive fixing head",(x,y,1.05),(.14,.14,.055),normal,center,"alloy",.022)
        for x in (-1.28,1.28):
            fitting("Flush lifting recess",(x,0,1.013),(.22,.68,.025),normal,center,"dark",.026)
            fitting("Lifting contact",(x,0,1.04),(.05,.43,.034),normal,center,"alloy",.012)
        fitting("Service stencil stripe",(.08,.92,1.013),(1.18,.08,.008),normal,center,"stencil",.004)
        # A recessed equipment cassette is surface-mounted; no unproven claim
        # that these louvers ventilate an exposed vacuum compartment.
        rear_normal=Vector((-.05547002,side*.9984604,0)).normalized()
        rear_center=Vector((-137,side*12.5,31.8))
        fitting("Aft equipment housing",(0,0,.57),(7.6,3.8,.35),rear_normal,rear_center,"armor",.08)
        fitting("Recessed equipment backing",(0,0,.93),(6.8,2.95,.055),rear_normal,rear_center,"dark",.04)
        for j in range(6):
            fitting("Equipment protective louver",(-2.7+j*1.08,0,1.02),(.36,2.6,.24),rear_normal,rear_center,"armor",.035)


def build(args):
    if sha(args.scene)!=CONFIG["input_sha256"]:raise SystemExit("Unexpected bridge-study-01 input")
    target=args.output.resolve()/"flagship-bridge-study-02.blend"
    if target.exists() and not args.overwrite:raise SystemExit("Output exists")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    if GROUP in bpy.data.collections:raise SystemExit("Already contains this revision")
    names=sorted(o.name for o in bpy.data.objects)
    before=fingerprint(names);room=archive_fingerprint();environment=contract()
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    base.collection(GROUP)
    base.MATERIALS.update({k:bpy.data.materials[v] for k,v in MATERIAL_MAP.items()})
    base.MATERIALS["armor"]=bpy.data.materials["SURFACE02_paint_0"]
    base.MATERIALS["alloy"]=bpy.data.materials["STUDY_alloy"]
    base.MATERIALS["stencil"]=bpy.data.materials["SURFACE02_stencil"]
    geometry()
    for name,c in CONFIG["cameras"].items():
        camera=base.camera(name,c["location"],c["target"],lens=c["lens"])
        camera.data.clip_end=100000000
    bpy.context.view_layer.update()
    assert fingerprint(names)==before and archive_fingerprint()==room and contract()==environment
    scene=bpy.context.scene
    scene.name="KUHAI — Bridge Side Structure and Coating 02"
    scene["revision"]=CONFIG["revision"]
    scene["bridge02_original_names"]=json.dumps(names)
    scene["bridge02_original_geometry"]=before
    scene.camera=bpy.data.objects["bridge_side"]
    scene.render.filepath="//previews/bridge_side.png"
    target.parent.mkdir(parents=True,exist_ok=True)
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users and image.packed_file:
            path=target.parent/"textures"/Path(image.filepath).name;path.parent.mkdir(exist_ok=True)
            path.write_bytes(image.packed_file.data);image.filepath="//textures/"+path.name
            for packed in image.packed_files:packed.filepath=image.filepath
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
    assert sha(args.scene)==CONFIG["input_sha256"]
    record={**CONFIG,"source_sha256":sha(target),"source_bytes":target.stat().st_size,
            "new_objects":len(bpy.data.collections[GROUP].objects),"source_objects_preserved":True,"blender":bpy.app.version_string}
    (target.parent/"bridge-finish-manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene=bpy.context.scene
    bpy.data.collections[GROUP].hide_render=args.previous
    bpy.data.collections[GROUP].hide_viewport=args.previous
    bpy.data.collections["ARCHIVE_SHELL"].hide_render=args.cutaway
    scene.render.resolution_x,scene.render.resolution_y=args.width,args.height
    scene.render.resolution_percentage=100
    scene.render.threads_mode,scene.render.threads="FIXED",6
    scene.cycles.samples,scene.cycles.use_adaptive_sampling=args.samples,False
    devices=select_device(scene,args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    record={"revision":CONFIG["revision"],"previous":args.previous,"cutaway":args.cutaway,"source_sha256":sha(args.scene),
            "width":args.width,"height":args.height,"samples":args.samples,"threads":6,"device":args.device,"devices":devices,"renders":[]}
    for name in args.views.split(","):
        path=args.output.resolve()/(name+".png")
        camera=bpy.data.objects.get(name)
        if not camera or camera.type!="CAMERA":raise SystemExit("Unknown camera")
        if path.exists() and not args.overwrite:raise SystemExit("Render exists")
        scene.camera,scene.render.filepath=camera,str(path)
        start=time.perf_counter();bpy.ops.render.render(write_still=True)
        record["renders"].append({"view":name,"seconds":round(time.perf_counter()-start,3),"peak_process_rss_mib":peak_process_rss_mib()})
        (args.output/"benchmark.json").write_text(json.dumps(record,indent=2)+"\n")
        print("FINISH_RENDER "+json.dumps(record["renders"][-1]),flush=True)


def inspect(args):
    if sha(args.baseline)!=CONFIG["input_sha256"]:raise SystemExit("Wrong baseline")
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    geometry,room,environment=fingerprint(names),archive_fingerprint(),contract()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    checks={"original_objects_preserved":fingerprint(names)==geometry,"archive_preserved":archive_fingerprint()==room,
            "environment_preserved":contract()==environment,"new_details_visible":not bpy.data.collections[GROUP].hide_render,
            "bridge01_old_hidden":bpy.data.collections["BRIDGE01_PREVIOUS"].hide_render,
            "new_cameras_perspective":all(bpy.data.objects[n].data.type=="PERSP" for n in CONFIG["cameras"])}
    issues,meshes,images=[],[],[]
    for obj in bpy.data.collections[GROUP].objects:
        bm=bmesh.new();bm.from_mesh(obj.data)
        volume=bm.calc_volume(signed=True)
        valid=volume>0 and all(e.is_manifold for e in bm.edges) and all(math.isfinite(v) for vert in bm.verts for v in vert.co)
        bm.free()
        if not valid:issues.append(obj.name+": invalid mesh")
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
        coords=[obj.matrix_world@v.co for v in mesh.vertices]
        bounds=[[min(v[i] for v in coords) for i in range(3)],[max(v[i] for v in coords) for i in range(3)]]
        if all(bounds[0][i]<(-61,-27,22.8)[i] and bounds[1][i]>(-99,-47,16.6)[i] for i in range(3)):
            issues.append(obj.name+": archive intrusion")
        meshes.append({"name":obj.name,"triangles":len(mesh.loop_triangles),"volume_m3":volume})
        evaluated.to_mesh_clear()
    for img in bpy.data.images:
        if img.type=="IMAGE" and img.users:
            valid=img.filepath.startswith("//") and bool(img.packed_file) and Path(bpy.path.abspath(img.filepath)).is_file()
            images.append({"name":img.name,"path":img.filepath,"portable":valid})
            if not valid:issues.append(img.name+": missing resource")
    checks["new_meshes_and_resources_valid"]=not issues
    record={"revision":CONFIG["revision"],"checks":checks,"issues":issues,"images":images,"meshes":meshes,
            "new_objects":len(meshes),"new_evaluated_triangles":sum(m["triangles"] for m in meshes),
            "browser_tested":False,"passed":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k!="meshes"},indent=2))
    if not record["passed"]:raise SystemExit(1)


if __name__=="__main__":
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    for command in ("build","render","inspect"):
        s=sub.add_parser(command);s.add_argument("--scene",type=Path,required=True);s.add_argument("--output",type=Path,required=True)
        s.add_argument("--overwrite",action="store_true")
        if command=="inspect":s.add_argument("--baseline",type=Path,required=True)
        if command=="render":
            s.add_argument("--views",default="overview,bridge_side,bridge_rear,bridge_finish_lit")
            s.add_argument("--width",type=int,default=960);s.add_argument("--height",type=int,default=600)
            s.add_argument("--samples",type=int,default=32);s.add_argument("--previous",action="store_true")
            s.add_argument("--cutaway",action="store_true");s.add_argument("--device",choices=("cpu","optix"),default="cpu")
    a=p.parse_args(argv)
    if a.command=="render" and not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):raise SystemExit("Invalid preview size")
    {"build":build,"render":render,"inspect":inspect}[a.command](a)
