"""Refine the bridge exterior from an immutable surface-study-03 scene.

No downloaded reference geometry, network, web export, or automatic GPU use.
The old bridge remains editable in a hidden comparison collection.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from form_study import contract, digest, object_record
from integration_study import MATERIAL_MAP, archive_fingerprint
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "bridge-study-01.json").read_text())
NEW, OLD = "BRIDGE01_EXTERIOR", "BRIDGE01_PREVIOUS"
PREFIX = "BRIDGE01 / "
REPLACED = ("Bridge foundation", "Bridge recessed observation belt",
            "Bridge shallow armored crown", "Bridge inset top",
            "Bridge central recessed service lid", "Bridge top access cover",
            "Bridge recessed window", "Bridge side support")
CX, RX, RY = CONFIG["center_x_m"], CONFIG["radius_x_m"], CONFIG["radius_y_m"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(names):
    # Blender leaves matrix_world unevaluated for a collection hidden at load.
    # Evaluate the retained comparison objects, then restore visibility; do not
    # treat their identity-matrix cache as an actual change of stored transform.
    old = bpy.data.collections.get(OLD)
    hidden = old.hide_viewport if old else None
    if old:
        old.hide_viewport = False
    bpy.context.view_layer.update()
    result = digest([object_record(bpy.data.objects[n]) for n in sorted(names)])
    if old:
        old.hide_viewport = hidden
        bpy.context.view_layer.update()
    return result


def finish(obj, part):
    obj.name = PREFIX + obj.name
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    bpy.data.collections[NEW].objects.link(obj)
    obj["role"], obj["bridge_part"] = "hull", part
    obj["revision"] = CONFIG["revision"]
    if obj.type == "MESH":
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
    return obj


def section(name, start, end, profile, material="armor", edge=.06, part="armor"):
    """Closed annular sector with an editable radial/height cross-section."""
    steps = max(2, math.ceil((end-start)/4))
    n = len(profile)
    verts = []
    for i in range(steps+1):
        angle = math.radians(start+(end-start)*i/steps)
        verts += [(CX+RX*r*math.cos(angle), RY*r*math.sin(angle), z) for r,z in profile]
    faces = [tuple(reversed(range(n))), tuple(range(steps*n,(steps+1)*n))]
    for k in range(steps):
        for j in range(n):
            faces.append((k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.data.collections[NEW].objects.link(obj)
    mesh.materials.append(base.MATERIALS[material])
    base.bevel(obj, edge)
    return finish(obj, part)


def oval(name, levels, material="armor", edge=.15, part="armor"):
    points = [(CX+RX*math.cos(2*math.pi*i/64),RY*math.sin(2*math.pi*i/64)) for i in range(64)]
    return finish(base.tapered_plate(name,points,levels,material,edge),part)


def box(name, loc, dims, material="armor", edge=.1, part="structure"):
    return finish(base.box(name,loc,dims,material,edge=edge),part)


def loft(name, sections, material="armor", edge=.15, part="structure"):
    return finish(base.loft(name,sections,material,edge),part)


def geometry():
    # A tapered plinth, with a dark shadow joint under the sill, replaces the
    # smooth cylindrical stack. Provisional scene meters are not canon scale.
    oval("Tapered bridge plinth",[(28.6,.89),(31.3,1.03),(34.8,1.01),(36.1,.96)],"armor",.18)
    oval("Recess below observation sill",[(35.7,.968),(36.6,.968)],"dark",.04)
    oval("Armored observation sill",[(36.35,.965),(36.9,1.015),(37.4,.995)],"paint",.09)
    oval("Observation gallery backing",[(36.8,.884),(41.2,.884)],"dark",.06,"recess")

    first,last = CONFIG["observation_arc_deg"]
    count = CONFIG["observation_bays"]
    step = (last-first)/count
    for i in range(count):
        a,b = first+i*step,last-(count-i-1)*step
        # Opaque shaded glazing proxy, not a modeled crew space or ray-traced
        # transparent room. Recess and window frames are real geometry.
        pane = section(f"Recessed observation pane {i+1:02d}",a+1.0,b-1.0,
                       [(.920,37.45),(.935,37.45),(.923,40.15),(.908,40.15)],
                       "glazing",.025,"glazing")
        pane["glazing_proxy"] = True
        # Only a few narrow warm interior traces: no unbroken emissive ring.
        if i in (1,4,7,8,11,14):
            section(f"Warm interior trace {i+1:02d}",a+2.0,b-2.0,
                    [(.934,37.7),(.937,37.7),(.936,38.08),(.933,38.08)],
                    "warm_glazing",.008,"window_light")
    for i in range(count+1):
        angle = first+i*step
        primary = i%4==0
        half = 1.0 if primary else .47
        section(f"Observation mullion {i:02d}",angle-half,angle+half,
                [(.87,36.8),(.995,36.8),(.986,40.6),(.87,41.1)],
                "paint" if primary else "dark",.055,"frame")
    section("Aft solid gallery enclosure",last+.5,first+360-.5,
            [(.87,36.8),(.96,36.8),(.94,41.2),(.87,41.2)],"armor",.1,"structure")

    # Twelve thick armor segments form an overhang, sloped crown, and rim.
    # Gaps remain restrained: at most 0.34 m along the nominal outer ellipse.
    hood = [(.89,40.65),(1.03,40.65),(1.045,41.7),(.936,43.65),(.79,44.5),(.79,42.6)]
    for i in range(12):
        section(f"Crown armor segment {i+1:02d}",i*30+.3,(i+1)*30-.3,
                hood,"paint",.09,"crown")
    oval("Inset crown shadow bed",[(42.4,.79),(43.9,.79)],"dark",.06,"recess")
    oval("Inset command roof",[(43.75,.765),(44.65,.722)],"armor",.1,"crown")

    # Longitudinal saddle ties the circular bridge to the retained dorsal crest.
    loft("Crown to crest saddle",[(-194,7,43.8,45.0,0),(-183,9,41.9,46.8,0),
         (-173,10,39.9,49.0,0),(-164,8,48.5,57.0,0)],"paint",.18)
    loft("Recessed dorsal saddle strip",[(-192,2.5,44.7,45.1,0),
         (-181,3.4,46.3,46.9,0),(-171,3.6,49.2,49.7,0)],"dark",.06,"recess")
    for side in (-1,1):
        loft("Swept bridge abutment",[(-193,2.2,29.5,36.7,side*26),
             (-179,3.5,26.4,42.9,side*25.5),(-165,4,25.3,48,side*23),
             (-146,2,23,36,side*18)],"armor",.17)
        loft("Abutment crest plate",[(-187,1.8,38.1,38.7,side*25.7),
             (-177,2.9,43.6,44.2,side*25.3),(-165,3.4,48.0,48.6,side*23)],"paint",.08)
        # Two small roof access plates serve scale, without tiling every face.
        o=box("Inset roof service gasket",(-196,side*12.1,44.66),(10,4,.13),"dark",.14,"service")
        box("Roof removable access plate",(-196,side*12.1,44.82),(9.4,3.4,.22),"paint",.09,"service")
        for x in (-199.6,-192.4):
            box("Roof flush lifting pocket",(x,side*12.1,44.946),(.7,1.1,.05),"dark",.045,"service")
    # Sparse lower armor facets articulate the chin without light striping.
    for i,(a,b) in enumerate(((68,111),(113,156),(158,202),(204,247),(249,292))):
        section(f"Bridge chin armor {i+1:02d}",a,b,
                [(1.01,31.5),(1.028,31.5),(1.009,34.6),(.991,34.6)],"paint",.07)


def compare(previous=False, cutaway=False):
    for name,visible in ((NEW,not previous),(OLD,previous)):
        bpy.data.collections[name].hide_render = not visible
        bpy.data.collections[name].hide_viewport = not visible
    bpy.data.collections["ARCHIVE_SHELL"].hide_render = cutaway
    bpy.context.view_layer.update()


def build(args):
    if sha(args.scene)!=CONFIG["input_sha256"]:
        raise SystemExit("Input must be the archived surface-study-03 scene")
    target = args.output.resolve()/"flagship-bridge-study-01.blend"
    if target.exists() and not args.overwrite:
        raise SystemExit("Output exists; use a new output directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    names = sorted(o.name for o in bpy.data.objects)
    before = fingerprint(names)
    room,environment = archive_fingerprint(),contract()
    for name in (NEW,OLD):
        if name in bpy.data.collections:
            raise SystemExit("Input already contains this study")
        base.collection(name)
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    base.MATERIALS.update({k:bpy.data.materials[v] for k,v in MATERIAL_MAP.items()})
    base.MATERIALS["armor"] = bpy.data.materials["SURFACE02_paint_0"]
    base.MATERIALS["paint"] = bpy.data.materials["SURFACE02_paint_1"]
    base.MATERIALS["glazing"] = base.material("BRIDGE01_glazing_proxy",(.037,.067,.071),0,.19,.10)
    base.MATERIALS["warm_glazing"] = base.material("BRIDGE01_warm_glazing",(.28,.14,.052),0,.28,1.2)
    removed = []
    for obj in list(bpy.data.collections["SHIP_HULL"].objects):
        if any(obj.name.startswith("FORM03 / "+p) for p in REPLACED):
            bpy.data.collections["SHIP_HULL"].objects.unlink(obj)
            bpy.data.collections[OLD].objects.link(obj)
            removed.append(obj.name)
    if len(removed)!=28:
        raise SystemExit(f"Unexpected bridge selection: {len(removed)} objects")
    geometry()
    for name,c in CONFIG["cameras"].items():
        camera=base.camera(name,c["location"],c["target"],lens=c["lens"])
        camera.data.clip_end = 100000000
    bpy.context.view_layer.update()
    assert fingerprint(names)==before
    assert archive_fingerprint()==room and contract()==environment
    compare()
    scene.name = "KUHAI — Bridge Structure Study 01"
    scene["revision"] = CONFIG["revision"]
    scene["bridge01_original_names"] = json.dumps(names)
    scene["bridge01_source_geometry"] = before
    scene["bridge01_room"],scene["bridge01_environment"] = room,environment
    scene.camera = bpy.data.objects["overview"]
    scene.render.filepath = "//previews/overview.png"
    target.parent.mkdir(parents=True,exist_ok=True)
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users and image.packed_file:
            path = target.parent/"textures"/Path(image.filepath).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(image.packed_file.data)
            image.filepath = "//textures/"+path.name
            for packed in image.packed_files:
                packed.filepath = image.filepath
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
    assert sha(args.scene)==CONFIG["input_sha256"]
    record = {**CONFIG,"original_objects_preserved":True,"replaced_objects":removed,
              "new_objects":len(bpy.data.collections[NEW].objects),
              "source_sha256":sha(target),"source_bytes":target.stat().st_size,
              "blender":bpy.app.version_string}
    (target.parent/"bridge-manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene=bpy.context.scene
    compare(args.previous,args.cutaway)
    scene.render.resolution_x,scene.render.resolution_y=args.width,args.height
    scene.render.resolution_percentage=100
    scene.render.threads_mode,scene.render.threads="FIXED",6
    scene.cycles.samples,scene.cycles.use_adaptive_sampling=args.samples,False
    devices=select_device(scene,args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    record={"revision":CONFIG["revision"],"previous":args.previous,"cutaway":args.cutaway,
            "source_sha256":sha(args.scene),"width":args.width,"height":args.height,
            "samples":args.samples,"threads":6,"device":args.device,"devices":devices,"renders":[]}
    for name in args.views.split(","):
        camera=bpy.data.objects.get(name)
        if camera is None or camera.type!="CAMERA":raise SystemExit("Unknown camera: "+name)
        path=args.output.resolve()/(name+".png")
        if path.exists() and not args.overwrite:raise SystemExit("Render already exists")
        scene.camera,scene.render.filepath=camera,str(path)
        start=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["renders"].append({"view":name,"seconds":round(time.perf_counter()-start,3),
                                  "peak_process_rss_mib":peak_process_rss_mib()})
        (args.output/"benchmark.json").write_text(json.dumps(record,indent=2)+"\n")
        print("BRIDGE_RENDER "+json.dumps(record["renders"][-1]),flush=True)


def inspect(args):
    if sha(args.baseline)!=CONFIG["input_sha256"]:raise SystemExit("Wrong baseline")
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    original,room,environment=fingerprint(names),archive_fingerprint(),contract()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene=bpy.context.scene
    checks={"baseline_original_objects_preserved":fingerprint(names)==original,
            "archive_interior_preserved":archive_fingerprint()==room,
            "lighting_planet_original_cameras_preserved":contract()==environment,
            "previous_bridge_hidden":bpy.data.collections[OLD].hide_render and bpy.data.collections[OLD].hide_viewport,
            "current_bridge_visible":not bpy.data.collections[NEW].hide_render,
            "archive_roof_ownership_preserved":"SURFACE03_ARCHIVE" in bpy.data.collections["ARCHIVE_SHELL"].children}
    checks["new_cameras_match_config"]=all(
        bpy.data.objects[n].data.type=="PERSP" and abs(bpy.data.objects[n].data.lens-c["lens"])<1e-5
        and (bpy.data.objects[n].location-Vector(c["location"])).length<1e-4
        for n,c in CONFIG["cameras"].items())
    meshes,issues=[],[]
    for obj in bpy.data.collections[NEW].objects:
        bm=bmesh.new();bm.from_mesh(obj.data)
        volume=bm.calc_volume(signed=True)
        valid=volume>0 and all(e.is_manifold for e in bm.edges) and all(math.isfinite(c) for v in bm.verts for c in v.co)
        bm.free()
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
        coords=[obj.matrix_world@v.co for v in mesh.vertices]
        bounds=[[min(v[i] for v in coords) for i in range(3)],[max(v[i] for v in coords) for i in range(3)]]
        if all(bounds[0][i]<(-61,-27,22.8)[i] and bounds[1][i]>(-99,-47,16.6)[i] for i in range(3)):
            issues.append(obj.name+": occupied archive intrusion")
        if not valid:issues.append(obj.name+": invalid closed mesh")
        meshes.append({"name":obj.name,"triangles":len(mesh.loop_triangles),"volume_m3":round(volume,6),"bounds":bounds})
        evaluated.to_mesh_clear()
    images=[]
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users:
            valid=image.filepath.startswith("//") and image.packed_file is not None and Path(bpy.path.abspath(image.filepath)).is_file()
            images.append({"name":image.name,"relative_path":image.filepath,"portable":valid})
            if not valid:issues.append(image.name+": nonportable resource")
    # Ray-test real geometry at three front/side bay centers. The first hit at
    # eye height must be a pane; the overhang must project farther outward.
    recess=[]
    deps=bpy.context.evaluated_depsgraph_get()
    for angle in (127.5,187.5,247.5):
        t=math.radians(angle)
        xy=Vector((RX*1.2*math.cos(t),RY*1.2*math.sin(t),0))
        direction=-xy.normalized()
        hits=[]
        for z in (38.7,41.5):
            origin=Vector((CX+xy.x,xy.y,z))
            hit,location,normal,index,obj,matrix=scene.ray_cast(deps,origin,direction,distance=20)
            hits.append({"object":obj.name if hit else None,"part":obj.get("bridge_part") if hit else None,
                         "distance_m":(location-origin).length if hit else None})
        depth=hits[0]["distance_m"]-hits[1]["distance_m"] if all(h["distance_m"] is not None for h in hits) else None
        valid=hits[0]["part"]=="glazing" and hits[1]["part"]=="crown" and depth is not None and depth>1.8
        recess.append({"angle_deg":angle,"hits":hits,"recess_m":depth,"passed":valid})
    checks["sampled_window_bays_recessed_and_visible"]=all(r["passed"] for r in recess)
    checks["new_geometry_and_resources_valid"]=not issues
    record={"revision":CONFIG["revision"],"checks":checks,"issues":issues,"images":images,
            "new_objects":len(meshes),"new_evaluated_triangles":sum(m["triangles"] for m in meshes),
            "meshes":meshes,"window_ray_checks":recess,"browser_tested":False,"passed":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k!="meshes"},indent=2))
    if not record["passed"]:raise SystemExit(1)


if __name__=="__main__":
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for command in ("build","render","inspect"):
        p=sub.add_parser(command)
        p.add_argument("--scene",type=Path,required=True)
        p.add_argument("--output",type=Path,required=True)
        p.add_argument("--overwrite",action="store_true")
        if command=="inspect":p.add_argument("--baseline",type=Path,required=True)
        if command=="render":
            p.add_argument("--views",default="overview,form_close,bridge_close,bridge_low")
            p.add_argument("--width",type=int,default=960)
            p.add_argument("--height",type=int,default=600)
            p.add_argument("--samples",type=int,default=32)
            p.add_argument("--device",choices=("cpu","optix"),default="cpu")
            p.add_argument("--previous",action="store_true")
            p.add_argument("--cutaway",action="store_true")
    a=parser.parse_args(argv)
    if a.command=="render" and not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):
        raise SystemExit("Invalid bounded render settings")
    {"build":build,"render":render,"inspect":inspect}[a.command](a)
