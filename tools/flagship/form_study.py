"""Revise the forebody without changing the integration study's lighting.

All geometry is authored here. Reference images are not imported or distributed.
Saved integration-study-01 is the reproducible, checksum-guarded input.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from integration_study import (MATERIAL_MAP, SHIP_GROUPS, archive_fingerprint,
                               checksum, switch_comparison)
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "form-study-03.json").read_text(encoding="utf-8"))
PREFIX = "FORM03 / "
REMOVE = ("Continuous armored keel", "Sloped forecastle", "Bridge ", "Recessed bridge window",
          "Fore shoulder", "Forward navigation slit", "Bow armored cheek", "Bow lateral",
          "Communications ", "Dorsal service channel", "Dorsal protected utility main",
          "Chamfered transverse spine rib", "Recessed lateral service panel",
          "Service panel upper armor lip", "Lower longitudinal armor belt",
          "Unassigned starboard service bay", "Starboard service roof", "Archive service pod lower hull")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def object_record(o):
    r = {"name": o.name, "type": o.type, "matrix": [list(row) for row in o.matrix_world]}
    if o.type == "MESH":
        r["vertices"] = [list(v.co) for v in o.data.vertices]
        r["faces"] = [list(p.vertices) for p in o.data.polygons]
        r["materials"] = [m.name if m else None for m in o.data.materials]
    if o.type == "LIGHT":
        r.update(kind=o.data.type, color=list(o.data.color), energy=o.data.energy,
                 angle=o.data.angle if o.data.type == "SUN" else None,
                 size=o.data.size if o.data.type == "AREA" else None)
    if o.type == "CAMERA":
        r.update(lens=o.data.lens, sensor=o.data.sensor_width, kind=o.data.type,
                 ortho=o.data.ortho_scale, clip=[o.data.clip_start, o.data.clip_end])
    return r


def contract():
    scene = bpy.context.scene
    groups = ("SPACE", "LIGHTING", "ROOM_LIGHTS", "PORT_DETAILS", "STARBOARD_DETAILS")
    records = {name: [object_record(o) for o in sorted(bpy.data.collections[name].objects, key=lambda o:o.name)]
               for name in groups}
    records["cameras"] = [object_record(bpy.data.objects[n]) for n in ("overview", "stern", "port", "detail")]
    records["display"] = [scene.view_settings.view_transform, scene.view_settings.look,
                          scene.view_settings.exposure, scene.view_settings.gamma]
    bg = scene.world.node_tree.nodes.get("Background")
    records["world"] = [list(bg.inputs[0].default_value), bg.inputs[1].default_value]
    return digest(records)


def exterior_fingerprint(baseline=False):
    objects = list(bpy.data.collections["BASELINE_SHIP"].objects) if baseline else [
        o for group in SHIP_GROUPS if group != "ARCHIVE_INTERIOR" for o in bpy.data.collections[group].objects]
    records = []
    for o in objects:
        r = object_record(o)
        if baseline:
            r["name"] = r["name"].removeprefix("BASELINE / ")
        records.append(r)
    return digest(sorted(records, key=lambda r:r["name"]))


def named(obj, group=None):
    obj.name = PREFIX + obj.name
    obj["form_revision"] = CONFIG["revision"]
    if group:
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        bpy.data.collections[group].objects.link(obj)
        obj["role"] = "archive_shell"
        obj["room_id"] = "archive"
    return obj


def loft(name, sections, mat="armor", edge=.55, group=None):
    return named(base.loft(name, sections, mat, edge), group)


def plate(name, outline, levels, mat="armor", edge=.55, group=None):
    return named(base.tapered_plate(name, outline, levels, mat, edge), group)


def box(name, loc, dims, mat="armor", edge=.2, group=None):
    return named(base.box(name, loc, dims, mat, edge=edge), group)


def ellipse(name, loc, radius, depth, scale, mat):
    o = named(base.cylinder(name, loc, radius, depth, mat, vertices=48))
    o.scale.x, o.scale.y = scale
    return o


def forebody():
    loft("Continuous tapered keel", [(-263, 10, -8, 3, 0), (-241, 31, -20, 14, 0),
         (-208, 40, -28, 23, 0), (-165, 36, -29, 22, 0), (-126, 29, -22, 12, 0),
         (9, 33, -24, 8, 0), (73, 48, -34, 14, 0), (174, 50, -33, 19, 0),
         (235, 26, -17, 13, 0)], edge=1.1)
    loft("Prow upper wedge", [(-260, 10, -2, 4, 0), (-236, 29, 2, 21, 0),
         (-204, 33, 10, 32, 0), (-173, 31, 9, 34, 0), (-146, 27, 8, 26, 0),
         (-126, 23, 7, 17, 0)], edge=.8)
    for side in (-1, 1):
        loft("Prow split armor strake", [(-258, 3, 3, 7, side*7),
             (-230, 7, 15, 21, side*14), (-213, 5, 25, 29, side*18)], "paint", .35)
        loft("Prow lower cheek", [(-253, 3, -15, -6, side*17),
             (-229, 5, -23, 4, side*32), (-206, 4, -26, 7, side*37),
             (-181, 3, -22, 6, side*35)], "paint", .6)
        # Sweep the broad shoulder toward a raised outer terminal, leaving a
        # narrow neck and a visible negative space aft of the forward arms.
        plan = [(-246, 30), (-231, 66), (-210, 106), (-191, 115),
                (-174, 99), (-147, 51), (-166, 29)]
        plan = [(x, y*side) for x,y in plan]
        plate("Swept forward shoulder body", plan, [(-18,.80),(-8,.97),(7,1),(22,.86)], edge=.9)
        plate("Forward shoulder recessed deck", plan, [(15,.87),(19,.91)], "dark", .2)
        # Two armor islands: broad root and narrow outer plate, separated by a
        # purposeful longitudinal service gap rather than a blanket slab.
        root = [(-232,32),(-219,59),(-193,70),(-162,47),(-175,31)]
        plate("Forward root armor island",[(x,y*side) for x,y in root],[(21,.96),(25,.84)],"paint",.4)
        outboard = [(-221,69),(-204,100),(-190,105),(-178,86),(-193,66)]
        plate("Forward outer armor island",[(x,y*side) for x,y in outboard],[(23,1),(26,.86)],"armor",.4)
        loft("Raised shoulder terminal", [(-221,4,-8,9,side*89),(-207,7,-12,38,side*103),
             (-192,7,-10,52,side*108),(-180,5,-5,39,side*100)], "armor", .65)
        loft("Shoulder terminal cap", [(-209,5,36,40,side*103),(-193,8,50,54,side*108),
             (-181,5,38,41,side*100)], "paint", .35)
        # Recessed optics occupy the raised terminal, with restrained emissive slits.
        panel=box("Terminal dark sensor face",(-200,side*111,39),(11,.6,5),"dark",.1)
        panel.rotation_euler[1] = -.35
        for x,z in ((-203,38),(-199,40),(-195,41.5)):
            box("Terminal optical slit",(x,side*111.4,z),(2,.25,.65),"cyan",.03)
        loft("Terminal leading armor trim",[(-215,1.2,22,27,side*99),
             (-203,1.4,41,46,side*106),(-193,1.4,51,53,side*108)],"edge",.18)
        for x in (-207,-201,-195):
            box("Fore armor maintenance recess",(x,side*78,26.2),(3,5,.35),"dark",.08)
        # New small forward turret remains subordinate to the shoulder silhouette.
        named(base.cylinder("Forward turret footing",(-211,side*56,26),4.5,2,"dark",vertices=24))
        loft("Forward turret shield",[(-217,3,27,30,side*56),(-207,4,27,33,side*56)],"paint",.3)
        for dy in (-1.4,1.4):
            named(base.cylinder("Forward turret barrel",(-221,side*56+dy,29.5),.5,15,"edge","X",vertices=12))
        for x in (-209,-199):
            box("Arm underside deck slit",(x,side*88,-5),(6,.45,.65),"amber",.04)

    # Elliptical, stepped bridge front backed by a tapered dorsal crest.
    # The exact circular bridge, floor arrangement and crest are interpretations.
    ellipse("Bridge foundation",(-193,0,32),27,9,(1.14,.88),"armor")
    ellipse("Bridge recessed observation belt",(-193,0,38.5),26,4,(1.14,.88),"dark")
    ellipse("Bridge shallow armored crown",(-193,0,41),25.6,2,(1.14,.88),"paint")
    ellipse("Bridge inset top",(-193,0,42.6),20.5,1.3,(1.14,.88),"armor")
    ellipse("Bridge central recessed service lid",(-190,0,43.35),9,.5,(1.2,.85),"dark")
    for side in (-1,1):
        box("Bridge top access cover",(-190,side*11,43.4),(9,3,.6),"armor",.25)
    for index in range(25):
        # Forward and side sectors; no full unbroken luminous ring.
        t = math.radians(42 + index*11.5)
        x,y = -193 + 29.65*math.cos(t), 22.9*math.sin(t)
        if index in (3,4,10,16,17,22):
            continue
        o=box("Bridge recessed window",(x,y,38.6),(2.8,.32,.78),"amber",.02)
        tangent=Vector((-29.65*math.sin(t),22.9*math.cos(t)))
        o.rotation_euler.z=math.atan2(tangent.y,tangent.x)
    loft("Dorsal command crest",[(-177,19,20,36,0),(-164,16,24,62,0),
         (-146,12,20,57,0),(-128,13,10,29,0),(-119,15,9,20,0)],edge=.65)
    loft("Crest sloped upper plate",[(-164,13,59,63,0),(-146,10,55,59,0),
         (-129,10,28,31,0)],"paint",.3)
    loft("Crest upper service inset",[(-161,5,60.4,61.1,0),(-150,5,58,58.7,0)],"dark",.12)
    for side in (-1,1):
        loft("Bridge side support",[(-188,3,15,23,side*28),(-166,6,10,32,side*28),
             (-139,4,4,23,side*25)],"armor",.35)
        named(base.cylinder("Recessed bridge equipment backing",(-152,side*29,16),9,2,"dark","Y",vertices=40))
        named(base.cylinder("Bridge equipment inset",(-152,side*30.2,16),6.5,.8,"edge","Y",vertices=32))
        # Sloped paneling instead of large bright decorative circles.
        for z in (11,16,21):
            box("Bridge equipment grille",(-152,side*30.8,z),(8,.3,.7),"dark",.05)
    named(base.cylinder("Short communication mast",(-148,0,64),.35,10,"edge",vertices=12))
    box("Mast receiver",(-148,0,66),(.5,6,.45),"edge",.08)


def midship():
    loft("Protected dorsal conduit bed",[(-133,16,7,17,0),(-106,17,8,19,0),
         (-28,18,8,19,0),(18,24,7,25,0),(44,25,11,29,0)],"dark",.45)
    for side in (-1,1):
        loft("Continuous dorsal edge spar",[(-136,2.8,14,22,side*19),
             (-110,3.3,18,27,side*21),(-39,3.2,18,25,side*23),
             (10,4,19,29,side*27),(38,4.5,22,31,side*31)],"armor",.4)
        for y in (5,10):
            named(base.cylinder("Protected utility main",(-53,side*y,18.5),.85,144,"edge","X",vertices=12))
    for x,w,top in ((-122,19,24),(-98,21,25),(-70,22,24),(-37,23,24),(-7,25,26),(23,29,31)):
        loft("Variable span transverse beam",[(x-2.5,w,17,top,0),(x+2.5,w,17,top,0)],"paint",.35)
        # Each beam has a narrow center clamping cap, keeping long quiet spans.
        box("Beam center keeper",(x,0,top+.7),(4.6,7,1.4),"armor",.2)
    for side in (-1,1):
        cy=side*37
        loft("Integrated service bay lower fairing",[(-137,4,-9,10,cy),(-117,14,-17,15.5,cy),
             (-100,18,-18,15.5,cy),(-57,18,-18,15.5,cy),(-38,13,-14,15.5,cy),
             (-17,4,-9,11,cy)],edge=.8)
        # Angled fore/aft adapters stop outside the protected occupied room.
        loft("Service bay forward adapter",[(-138,4,9,17,cy),(-119,13,11,23,cy),
             (-109,16,13,27,cy)],edge=.5)
        loft("Service bay aft adapter",[(-48,16,12,27,cy),(-35,11,9,22,cy),
             (-15,4,8,17,cy)],edge=.5)
        group="ARCHIVE_SHELL" if side==-1 else None
        roof=[(-114,21),(-108,51),(-94,55),(-58,55),(-43,45),(-43,25),(-57,19.8),(-100,19.8)]
        plate("Port bay removable fitted roof" if side==-1 else "Starboard fitted bay roof",
              [(x,y*side) for x,y in roof],[(26.1,1),(29.2,.95)],"paint",.35,group)
        wall=[(-114,49),(-95,55.5),(-59,55.5),(-44,47.5),(-44,45.5),(-60,53.3),(-95,53.3),(-114,46.8)]
        o=named(base.prism("Bay removable shaped outer wall" if side==-1 else "Starboard shaped outer wall",
                    [(x,y*side) for x,y in wall],15.7,26.2,"armor",edge=.3),group)
        # Cutaway owns the wall's fittings too; removing it leaves no floating grille.
        for x in (-99,-80,-61):
            box("Bay recessed service strip",(x,side*55.7,20.5),(12,.35,2.6),"dark",.08,group)
            if x!=-80:
                box("Bay small working light",(x,side*55.95,21),(3,.15,.45),"amber",.02,group)
        for x in (-103,-60):
            box("Bay roof lock",(x,side*38,29.35),(3,6,.5),"edge",.15,group)
        for x in (-127,-28):
            loft("Lower lateral armor rail",[(x-9,2,-18,-13,side*33),(x+9,2,-18,-13,side*33)],"paint",.3)
        # Low swept bridge into the unchanged rear shoulder, far behind archive.
        outline=[(-32,25),(-10,39),(28,61),(48,52),(28,33),(-13,24)]
        plate("Midship to aft shoulder fillet",[(x,y*side) for x,y in outline],[(5,.94),(17,1),(23,.78)],"armor",.6)


def build(a):
    out=a.output.resolve()
    target=out/"flagship-form-study-03.blend"
    if target.exists() and not a.overwrite:
        raise SystemExit("Output already exists; use a fresh directory")
    if checksum(a.scene)!=CONFIG["input_sha256"]:
        raise SystemExit("Expected the unchanged integration-study-01 input; do not overwrite an artist's later edits")
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene=bpy.context.scene
    before=contract()
    archive_before=archive_fingerprint()
    exterior_before=exterior_fingerprint()
    # Replace the old blockout comparison with the immediate prior integration.
    baseline=bpy.data.collections["BASELINE_SHIP"]
    # Newly linked copies need one evaluated visible update before hiding;
    # otherwise their stored matrix_world remains identity until first reveal.
    baseline.hide_viewport=baseline.hide_render=False
    for o in list(baseline.objects):
        bpy.data.objects.remove(o,do_unlink=True)
    for group in SHIP_GROUPS:
        if group=="ARCHIVE_INTERIOR":
            continue
        for o in list(bpy.data.collections[group].objects):
            copy=o.copy()
            copy.name="BASELINE / "+o.name
            baseline.objects.link(copy)
    removed=[]
    for o in list(bpy.data.collections["SHIP_HULL"].objects):
        points=[o.matrix_world @ Vector(p) for p in o.bound_box]
        forward_turret=o.name.startswith(("Turret mounting ring","Sloped turret cradle","Turret barrel placeholder")) and max(p.x for p in points)<-180
        if o.name.startswith(REMOVE) or forward_turret:
            removed.append(o.name)
            bpy.data.objects.remove(o,do_unlink=True)
    for o in list(bpy.data.collections["ARCHIVE_SHELL"].objects):
        removed.append(o.name)
        bpy.data.objects.remove(o,do_unlink=True)
    base.COLLECTIONS.clear()
    base.COLLECTIONS.update({c.name:c for c in scene.collection.children})
    base.MATERIALS.clear()
    base.MATERIALS.update({m.name:m for m in bpy.data.materials})
    base.MATERIALS.update({old:bpy.data.materials[new] for old,new in MATERIAL_MAP.items()})
    forebody()
    midship()
    for name,data in CONFIG["extra_cameras"].items():
        o=base.camera(name,data["position"],data["target"],lens=data.get("lens",44),ortho=data.get("ortho"))
        o.data.clip_end=100000000
    bpy.context.view_layer.update()
    assert contract()==before
    assert archive_fingerprint()==archive_before
    scene["form_preserved_contract"]=before
    scene["form_archive_fingerprint"]=archive_before
    scene["form_baseline_fingerprint"]=exterior_before
    scene["comparison_baseline"]="integration-study-01"
    scene["revision"]=CONFIG["revision"]
    scene["status"]=CONFIG["status"]
    scene.name="KUHAI — Forebody Form Study 03"
    scene.camera=bpy.data.objects["overview"]
    scene.render.filepath="//renders/overview.png"
    switch_comparison(False)
    out.mkdir(parents=True,exist_ok=True)
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.packed_file and image.users:
            path=out/"textures"/Path(image.filepath).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(image.packed_file.data)
            image.filepath="//textures/"+path.name
            for packed in image.packed_files:
                packed.filepath=image.filepath
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
    report={**CONFIG,"blender":bpy.app.version_string,"input_filename":a.scene.name,
            "source_bytes":target.stat().st_size,"source_sha256":checksum(target),
            "removed_objects":removed,"new_objects":sum(o.name.startswith(PREFIX) for o in scene.objects),
            "preserved_contract":before,"archive_fingerprint":archive_before,
            "baseline_exterior_fingerprint":exterior_before,
            "comparison_baseline":"integration-study-01","gpu_used":False}
    (out/"form-manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("FORM_BUILD "+json.dumps({k:report[k] for k in ("source_bytes","source_sha256","new_objects")}))


def render(a):
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene=bpy.context.scene
    views=a.views.split(",")
    if any(v not in bpy.data.objects or bpy.data.objects[v].type!="CAMERA" for v in views):
        raise SystemExit("Unknown camera")
    if not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):
        raise SystemExit("Invalid render settings")
    out=a.output.resolve()
    if not a.overwrite and any((out/(v+".png")).exists() for v in views):
        raise SystemExit("Render exists; use a fresh directory")
    if a.baseline and a.cutaway:
        raise SystemExit("Baseline cutaway is not a supported comparison")
    out.mkdir(parents=True,exist_ok=True)
    switch_comparison(a.baseline)
    if a.cutaway:
        bpy.data.collections["ARCHIVE_SHELL"].hide_render=True
    scene.render.resolution_x,scene.render.resolution_y=a.width,a.height
    scene.render.resolution_percentage=100
    scene.cycles.samples=a.samples
    scene.cycles.use_adaptive_sampling=False
    scene.render.threads_mode="FIXED"
    scene.render.threads=6
    devices=select_device(scene,a.device)
    report={"revision":CONFIG["revision"],"baseline":a.baseline,"cutaway":a.cutaway,
            "source_sha256":checksum(a.scene),
            "width":a.width,"height":a.height,"samples":a.samples,"threads":6,
            "device":a.device,"devices":devices,"blender":bpy.app.version_string,"renders":[],
            "browser_tested":False}
    for name in views:
        scene.camera=bpy.data.objects[name]
        scene.render.filepath=str(out/(name+".png"))
        start=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        report["renders"].append({"view":name,"seconds":round(time.perf_counter()-start,3),
                                  "peak_process_rss_mib":peak_process_rss_mib()})
        (out/"benchmark.json").write_text(json.dumps(report,indent=2)+"\n")
        print("FORM_RENDER "+json.dumps(report["renders"][-1]),flush=True)


def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for command in ("build","render"):
        q=sub.add_parser(command)
        q.add_argument("--scene",type=Path,required=True)
        q.add_argument("--output",type=Path,required=True)
        q.add_argument("--overwrite",action="store_true")
        if command=="render":
            q.add_argument("--views",default="overview,port,form_close,form_top")
            q.add_argument("--width",type=int,default=960)
            q.add_argument("--height",type=int,default=600)
            q.add_argument("--samples",type=int,default=32)
            q.add_argument("--device",choices=("cpu","optix"),default="cpu")
            q.add_argument("--baseline",action="store_true")
            q.add_argument("--cutaway",action="store_true")
    a=p.parse_args(argv)
    build(a) if a.command=="build" else render(a)


if __name__=="__main__":
    main()
