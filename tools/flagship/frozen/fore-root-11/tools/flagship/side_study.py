"""Port bridge service-structure sample from immutable home-look-01.

Builds editable booleans, real recessed equipment and functional connections.
The original host is retained, material shaders are shared simple PBR, and
all previews use CPU unless a device is explicitly selected. No network use.
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from bridge_study import sha
from form_study import contract, digest, object_record
from home_look import node_record
from integration_study import archive_fingerprint
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "side-study-03.json").read_text())
NEW, OLD, CUTTERS = "SIDE03_STRUCTURE", "SIDE03_PREVIOUS", "SIDE03_CUTTERS"
PREFIX = "SIDE03 / "
PARTS = []
BAYS = [
    [(-188, 31.1), (-175.8, 29.4), (-175.8, 39.3), (-178.2, 39.8), (-188, 35.8)],
    [(-173.4, 29.0), (-154.8, 26.7), (-154.8, 37.1), (-164.7, 44.4), (-173.4, 41.2)],
]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def protected(names):
    states = {c.name: c.hide_viewport for c in bpy.data.collections}
    for c in bpy.data.collections:
        c.hide_viewport = False
    bpy.context.view_layer.update()
    records = []
    for name in names:
        o = bpy.data.objects[name]
        row = object_record(o)
        row["slots"] = [s.material.name if s.material else None for s in o.material_slots]
        records.append(row)
    for name, state in states.items():
        bpy.data.collections[name].hide_viewport = state
    bpy.context.view_layer.update()
    return digest(records)


def finish(o, function, material=None):
    if not o.name.startswith(PREFIX):
        o.name = PREFIX + o.name
    base.place(o, NEW, material)
    o["revision"], o["function"] = CONFIG["revision"], function
    if o.type == "MESH":
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(o.data)
        bm.free()
    PARTS.append(o.name)
    return o


def box(name, loc, dims, mat="s_paint", edge=.07, function="service enclosure"):
    return finish(base.box(name, loc, dims, mat, NEW, edge), function)


def xz_prism(name, points, front, back, mat="s_paint", edge=.07, function="armor"):
    # Local XY becomes world XZ; positive local Z points toward the port viewer.
    obj = base.prism(name, points, -back, -front, mat, NEW, edge)
    obj.matrix_world = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    return finish(obj, function)


def beam(name, a, b, width, depth, mat="s_metal", function="load path"):
    a, b = Vector(a), Vector(b)
    o = box(name, (a+b)/2, (width, depth, (b-a).length), mat, min(width, depth)*.16, function)
    o.rotation_euler = (b-a).to_track_quat("Z", "Y").to_euler()
    return o


def pipe(name, points, radius=.12, mat="s_pipe"):
    # Smooth tangent directions across straight polyline segments; no curves in web export.
    points = [Vector(p) for p in points]
    verts, sides = [], 10
    for i, p in enumerate(points):
        tangent = (points[min(i+1, len(points)-1)]-points[max(i-1, 0)]).normalized()
        u = tangent.cross(Vector((0, 0, 1)))
        if u.length < .1:
            u = tangent.cross(Vector((0, 1, 0)))
        u.normalize()
        v = tangent.cross(u).normalized()
        for j in range(sides):
            t = 2*math.pi*j/sides
            verts.append(p + radius*(math.cos(t)*u + math.sin(t)*v))
    faces = [tuple(reversed(range(sides))), tuple(range(len(verts)-sides, len(verts)))]
    for i in range(len(points)-1):
        for j in range(sides):
            faces.append((i*sides+j, i*sides+(j+1)%sides, (i+1)*sides+(j+1)%sides, (i+1)*sides+j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(base.MATERIALS[mat])
    obj = bpy.data.objects.new(name, mesh)
    bpy.data.collections[NEW].objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = len(p.vertices) == 4
    return finish(obj, "routed connection with defined endpoints")


def surface_y(x):
    if x < -179:
        return -29 + (-179-x)*.8/14
    if x <= -165:
        return -29 + (x+179)*2/14
    return -27 + (x+165)*7/19


def fastener(x, y, z, radius=.17):
    return finish(base.cylinder("Captive hex fixing", (x, y, z), radius, .13, "s_metal", "Y", NEW, vertices=6), "removable service attachment")


def materials():
    specs = {
        "s_paint": ((.08,.107,.127), .06,.46),
        "s_repair": ((.125,.143,.143), .04,.55),
        "s_dark": ((.017,.026,.032), .35,.58),
        "s_metal": ((.25,.31,.35), .82,.31),
        "s_pipe": ((.09,.125,.14), .75,.39),
        "s_seal": ((.009,.011,.014), 0,.75),
        "s_mark": ((.60,.33,.095), .08,.50),
        "s_label": ((.48,.54,.52), 0,.60),
    }
    for key, (color, metal, rough) in specs.items():
        mat = base.material(PREFIX+key, color, metal, rough)
        base.MATERIALS[key] = mat
    base.MATERIALS["s_lamp"] = base.material(PREFIX+"warm service lamp", (.8,.36,.10), 0,.35,1.7)


def geometry():
    host = bpy.data.objects[CONFIG["host"]]
    revised = host.copy()
    revised.data = host.data.copy()
    revised.name = PREFIX+"Opened structural abutment"
    bpy.data.collections[NEW].objects.link(revised)
    revised.modifiers.clear()
    revised["role"], revised["function"] = "hull", "primary bridge support around two service apertures"
    for coll in list(host.users_collection):
        coll.objects.unlink(host)
    bpy.data.collections[OLD].objects.link(host)
    for i, poly in enumerate(BAYS):
        cutter = xz_prism(f"Aperture tool {i}", poly, -40, 0, "s_dark", 0)
        for c in list(cutter.users_collection):
            c.objects.unlink(cutter)
        bpy.data.collections[CUTTERS].objects.link(cutter)
        cutter.display_type = "WIRE"
        cutter.hide_render = True
        mod = revised.modifiers.new(f"Editable service opening {i}", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cutter
        # Back wall is behind the support; empty depth is real geometry.
        xz_prism(f"Service bay pressure boundary {i}", poly, -20.1 if i==0 else -16.2,
                 -19.8 if i==0 else -15.9, "s_dark", .04, "sealed boundary behind unpressurized equipment recess")
    base.bevel(revised, .12, 3)
    PARTS.append(revised.name)

    # Frames follow the opening contour, providing readable depth and attachment.
    for i, poly in enumerate(BAYS):
        for a, b in zip(poly, poly[1:]+poly[:1]):
            pa, pb = (a[0], surface_y(a[0])-.08, a[1]), (b[0], surface_y(b[0])-.08, b[1])
            beam(f"Bay {i} gasket edge", pa, pb, .32, .24, "s_seal", "aperture perimeter isolation")
            beam(f"Bay {i} retaining edge", (pa[0],pa[1]-.16,pa[2]), (pb[0],pb[1]-.16,pb[2]), .11,.13)
        for x,z in poly:
            fastener(x, surface_y(x)-.3, z)

    # First bay: three replaceable electronics cassettes attached to a carrier.
    beam("Avionics lower carrier", (-187,-22.0,32),(-177,-22.0,30.8), .44,.42)
    for i, x in enumerate((-185.5,-182.1,-178.7)):
        z = 33.1 + i*.12
        box("Isolated cassette cradle", (x,-23.0,z), (2.8,2.5,4.5), "s_metal", .16)
        box("Replaceable electronics module", (x,-24.48,z+.12), (2.34,.5,3.8), "s_pipe", .13)
        box("Inset module face", (x,-24.77,z+.12), (1.96,.13,3.2), "s_dark", .05)
        for j in range(5):
            box("Module face protective rib", (x,-24.91,z-1.05+j*.51),(1.62,.12,.09),"s_metal",.02)
        box("Module identity strip", (x,-25.0,z+1.54),(.72,.025,.13),"s_label",.005)
        for zz in (z-1.42,z+1.62):
            fastener(x+.83,-24.96,zz,.11)
            beam("Cassette rear mounting arm",(x,-22.0,zz),(x,-19.9,zz),.38,.42,"s_pipe","equipment load into bay boundary")
        pipe("Cassette routed connection",[(x,-24.0,z-2.0),(x,-24.0,30),(x+.45,-23,29.6),(-176.4,-23,29.6)],.105)
    box("Carrier junction",(-176.3,-23,29.6),(1.1,1.1,1.2),"s_mark",.10)

    # Second bay: manifold, coupled vertical actuators and a protected trunk.
    for x in (-172,-167,-162,-157):
        y=surface_y(x)+5.8
        beam("Secondary equipment carrier",(x,y,30.1),(x,y,39.1 if x < -160 else 35.4),.28,.35,"s_pipe")
    pipe("Upper segmented manifold",[(-173,-21.5,40.4),(-170,-21.5,40.4),
         (-163,-20.6,40.4),(-158.8,-19.0,37.8),(-155.5,-18.4,36.7)],.24)
    for i,x in enumerate((-169.6,-163.9,-158.8)):
        y = surface_y(x)+2.1
        z = 33.8 if i<2 else 31.8
        box("Manifold mounting shoe",(x,y+1.0,z),(3.7,1.0,6.5),"s_dark",.13)
        canister=base.cylinder("Vertical service cylinder",(x,y,z),.85,4.1,"s_metal","Z",NEW,vertices=24)
        finish(canister,"replaceable actuator or fluid-system subassembly; fictional equipment")
        for dz in (-1.8,1.8):
            box("Cylinder restraint",(x,y-.05,z+dz),(2.35,1.95,.29),"s_pipe",.06)
            fastener(x+.93,y-1.06,z+dz,.13)
        upper=40.4 if i<2 else 37.8
        upper_y=-21.5+(x+170)*.9/7 if i<2 else -19.0
        pipe("Upper manifold connector",[(x,y,z+2.12),(x,y,z+2.65),
             (x,y+.35,z+3.0),(x,y+.35,upper-.55),(x,upper_y,upper)],.20)
        for zz in (z-1.8,z+1.8):
            beam("Cylinder rear mounting arm",(x,y+.65,zz),(x,-16.1,zz),.40,.48,"s_pipe","restraint transfers load to bay structure")
        for zz in (z-1.55,z+1.55):
            finish(base.cylinder("Cylinder split collar",(x,y,zz),.94,.22,"s_dark","Z",NEW,vertices=24),"removable coupling collar")
        box("Cylinder label",(x,y-.864,z),(.68,.025,.42),"s_label",.015)
        for j in range(3):
            box("Cylinder label line",(x,y-.89,z-.10+j*.095),(.41,.02,.025),"s_dark",.005)
        pipe("Lower fluid return",[(x,y,z-2.1),(x,y,28.8),(x+1,y+.4,28.1),(-153.7,-17.5,28.1)],.12)
    box("Upper manifold distributor",(-163.9,-20.6,40.4),(1.55,1.2,1.0),"s_pipe",.12)
    box("Aft electrical trunk",(-153.6,-17.5,28.2),(1.8,2.1,1.4),"s_dark",.15)
    for x,z0,z1 in ((-174.5,27.7,42.4),(-153.8,26.4,39.0)):
        y=surface_y(x)-.18
        beam("Primary diagonal load rib",(x-1,y,z0),(x+1.25,y+.5,z1),.54,.72,"s_paint")

    # Upper armored lip and a single offset repair panel keep broad quiet areas.
    xz_prism("Forward overlapping armor",[(-191.5,36.7),(-178.4,42.9),(-177.5,44.2),(-188.3,39.4)],-29.2,-27.9,"s_paint",.12)
    xz_prism("Aft overlapping armor",[(-174.0,43.6),(-165.1,48.0),(-153.3,40.0),(-152.2,41.0),(-164.6,49.4),(-174.1,45.1)],-25.6,-24.4,"s_repair",.13)
    # Horizontal service sill: human-scaled footholds, no occupied exterior balcony.
    beam("Service attachment rail",(-188,-29.6,29.7),(-153.5,-20.5,25.7),.34,.48,"s_metal","external maintenance tether and attachment rail")
    for x,z in ((-185,29.2),(-180,28.6),(-175,28.1),(-170,27.5),(-165,27.0),(-160,26.5)):
        y=surface_y(x)-.25
        box("Service rail bracket",(x,y,z),(.75,1.0,.4),"s_dark",.07)
        box("Maintenance index mark",(x,y-.57,z),(.38,.025,.13),"s_mark",.01)
    for x,z in ((-181.2,39.45),(-162.2,43.6)):
        y=surface_y(x)-.55
        box("Recessed worklight hood",(x,y,z),(2.2,.6,.45),"s_dark",.09)
        box("Shielded service emitter",(x,y-.315,z-.08),(1.42,.045,.10),"s_lamp",.02)
    # Visible attachment pads and fasteners tie the large support to the hull.
    for x,z in ((-190.1,34.8),(-175.0,35.0),(-151.7,33.0)):
        y=surface_y(x)-.45
        box("Structural attachment pad",(x,y,z),(1.9,.32,2.7),"s_repair",.14)
        for dx in (-.59,.59):
            for dz in (-.90,.90):
                fastener(x+dx,y-.20,z+dz,.17)
    # Small replaceable lower shield, spaced from the continuous main armor.
    xz_prism("Removable equipment shield",[(-172.1,34.0),(-166.0,33.5),(-166.0,35.1),(-172.1,35.6)],
             -28.3,-27.8,"s_paint",.09,"local debris guard without sealing the service aperture")
    for x,z in ((-171.5,35.0),(-166.6,34.5)):
        fastener(x,-28.43,z,.13)
        beam("Shield stand-off",(x,-28.0,z),(x,-16.1,z),.25,.31,"s_dark","debris guard attachment")


def cameras():
    for name, c in CONFIG["cameras"].items():
        if name not in bpy.data.objects:
            base.camera(name,c["position"],c["target"],lens=c["lens"])


def build(args):
    if sha(args.scene) != CONFIG["input_sha256"]:
        raise SystemExit("Input must be the immutable home-look-01 source")
    target = args.output / "flagship-side-study-03.blend"
    if target.exists():
        raise SystemExit("Output exists; use a new directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    before, room, lighting = protected(names), archive_fingerprint(), contract()
    mats = {m.name:digest(node_record(m)) for m in bpy.data.materials}
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    for name in (NEW,OLD,CUTTERS):
        base.collection(name)
    materials()
    geometry()
    bpy.data.collections[OLD].hide_render=True
    bpy.data.collections[OLD].hide_viewport=True
    # Cutters must remain dependency-evaluable, although individually invisible.
    bpy.data.collections[CUTTERS].hide_render=True
    cameras()
    assert protected(names)==before
    assert archive_fingerprint()==room and contract()==lighting
    assert all(digest(node_record(bpy.data.materials[n]))==v for n,v in mats.items())
    scene=bpy.context.scene
    scene.name,scene["revision"]="KUHAI — Port Bridge Structure 03", CONFIG["revision"]
    scene["side03_original_names"]=json.dumps(names)
    scene.camera=bpy.data.objects["side03_context"]
    target.parent.mkdir(parents=True,exist_ok=True)
    for img in bpy.data.images:
        if img.type=="IMAGE" and img.users:
            if not img.packed_file: raise RuntimeError("Missing packed texture")
            path=target.parent/"textures"/Path(img.filepath).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(img.packed_file.data)
            img.filepath="//textures/"+path.name
            for packed in img.packed_files: packed.filepath=img.filepath
    scene.render.filepath="//previews/side03_context.png"
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(target.resolve()),compress=True,relative_remap=False)
    write(target.parent/"side-manifest.json",{**CONFIG,"sha256":sha(target),"bytes":target.stat().st_size,
          "new_objects":len(bpy.data.collections[NEW].objects),"original_objects_preserved":True,
          "archive_and_lighting_preserved":True,"blender":bpy.app.version_string})
    print("SIDE_BUILD",sha(target),flush=True)


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    cameras()
    if NEW in bpy.data.collections:
        bpy.data.collections[NEW].hide_render=args.previous
        bpy.data.collections[OLD].hide_render=not args.previous
    scene=bpy.context.scene
    if args.web_model:
        if args.previous: raise SystemExit("A previous-source comparison cannot replace the ship with a new web model")
        names=set(o.name for o in bpy.data.objects)
        for o in list(bpy.data.objects):
            if o.type=="MESH" and not any(c.name=="SPACE" for c in o.users_collection):
                o.hide_render=True
        bpy.ops.import_scene.gltf(filepath=str(args.web_model.resolve()))
        imported=[o for o in bpy.data.objects if o.name not in names]
        for o in imported:
            if o.parent not in imported:
                o.matrix_world=Matrix.Scale(100,4)@o.matrix_world
        bpy.context.view_layer.update()
    if args.neutral:
        for o in list(bpy.data.collections["LIGHTING"].all_objects):
            o.hide_render=True
        source=base.light("SIDE03 neutral key","AREA",(-210,-95,115),(-172,-22,37),42000,(1,1,1),45)
        fill=base.light("SIDE03 neutral fill","AREA",(-135,-50,57),(-172,-22,37),16000,(.72,.82,1),30)
        scene.view_settings.exposure=.65
        bpy.data.collections["SPACE"].hide_render=True
    scene.render.resolution_x,scene.render.resolution_y=args.width,args.height
    scene.render.resolution_percentage=100
    scene.render.threads_mode,scene.render.threads="FIXED",6
    scene.cycles.samples,scene.cycles.use_adaptive_sampling=args.samples,False
    devices=select_device(scene,args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    record={"revision":CONFIG["revision"],"previous":args.previous,"neutral":args.neutral,
            "width":args.width,"height":args.height,"samples":args.samples,"device":args.device,"devices":devices,"renders":[]}
    if args.web_model: record["web_model_sha256"]=sha(args.web_model)
    for view in args.views.split(","):
        path=args.output/(view+".png")
        if path.exists(): raise SystemExit("Render exists")
        scene.camera,scene.render.filepath=bpy.data.objects[view],str(path.resolve())
        start=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["renders"].append({"view":view,"seconds":round(time.perf_counter()-start,3),"rss_mib":peak_process_rss_mib()})
        write(args.output/"benchmark.json",record)
        print("SIDE_RENDER "+json.dumps(record["renders"][-1]),flush=True)


def inspect(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    before,room,lighting=protected(names),archive_fingerprint(),contract()
    mats={m.name:digest(node_record(m)) for m in bpy.data.materials}
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    checks={"input_sha":sha(args.baseline)==CONFIG["input_sha256"],"original_objects":protected(names)==before,
            "archive":archive_fingerprint()==room,"lighting":contract()==lighting,
            "materials":all(digest(node_record(bpy.data.materials[n]))==v for n,v in mats.items())}
    bpy.context.view_layer.update()
    meshes=[]
    for obj in bpy.data.collections[NEW].objects:
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh(); mesh.calc_loop_triangles()
        bm=bmesh.new(); bm.from_mesh(mesh)
        valid=bool(bm.faces) and bm.calc_volume(signed=True)>0 and all(e.is_manifold for e in bm.edges)
        meshes.append({"name":obj.name,"valid_closed_volume":valid,"triangles":len(mesh.loop_triangles)})
        bm.free(); evaluated.to_mesh_clear()
    checks["closed_meshes"]=all(m["valid_closed_volume"] for m in meshes)
    checks["portable_images"]=all(img.packed_file and img.filepath.startswith("//") and Path(bpy.path.abspath(img.filepath)).is_file()
        for img in bpy.data.images if img.type=="IMAGE" and img.users)
    checks["old_hidden"]=bpy.data.collections[OLD].hide_render
    checks["new_visible"]=not bpy.data.collections[NEW].hide_render
    write(args.output,{"checks":{k:bool(v) for k,v in checks.items()},"passed":all(checks.values()),"meshes":meshes,
          "triangles":sum(m["triangles"] for m in meshes),"browser_tested":False})
    print(json.dumps({"checks":{k:bool(v) for k,v in checks.items()},"invalid":[m["name"] for m in meshes if not m["valid_closed_volume"]]}))
    if not all(checks.values()): raise SystemExit(1)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for command in ("build","render","inspect"):
        a=sub.add_parser(command)
        a.add_argument("--scene",type=Path,required=True)
        a.add_argument("--output",type=Path,required=True)
        if command=="inspect": a.add_argument("--baseline",type=Path,required=True)
        if command=="render":
            a.add_argument("--views",default="side03_context,side03_detail")
            a.add_argument("--width",type=int,default=960)
            a.add_argument("--height",type=int,default=600)
            a.add_argument("--samples",type=int,default=32)
            a.add_argument("--device",choices=("cpu","optix"),default="cpu")
            a.add_argument("--web-model",type=Path)
            a.add_argument("--previous",action="store_true")
            a.add_argument("--neutral",action="store_true")
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args=p.parse_args(argv)
    globals()[args.command](args)

