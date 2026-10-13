"""Reversible exterior finish, shared stellar light and fixed homepage cameras.

Requires Blender 4.5.14. No downloads, web export, camera animation or GPU default.
Original materials remain intact; exterior slots use object-level overrides.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from bridge_study import sha
from form_study import digest, object_record
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "home-look-01.json").read_text())
PREFIX = "HOME01 / "
PLANETS = ("Fictional planetary surface", "Procedural cloud shell", "Thin lit-limb preview shell")


def scalar(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def node_record(material):
    if not material.use_nodes:
        return list(material.diffuse_color)
    nodes = []
    for n in material.node_tree.nodes:
        row = {"name": n.name, "type": n.bl_idname,
               "inputs": [(s.identifier, scalar(s.default_value)) for s in n.inputs if hasattr(s, "default_value")]}
        for key in ("operation", "blend_type", "projection", "interpolation", "noise_dimensions"):
            if hasattr(n, key):
                row[key] = getattr(n, key)
        if n.type == "VALTORGB":
            row["ramp"] = [(e.position, list(e.color)) for e in n.color_ramp.elements]
        if n.type == "TEX_IMAGE":
            row["image"] = n.image.name if n.image else None
        nodes.append(row)
    links = [(l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
             for l in material.node_tree.links]
    return {"nodes": nodes, "links": sorted(links)}


def snapshot():
    # Evaluate hidden comparison collections as well, then restore visibility.
    hidden = {c.name: c.hide_viewport for c in bpy.data.collections}
    for c in bpy.data.collections:
        c.hide_viewport = False
    bpy.context.view_layer.update()
    geometry, cameras = {}, {}
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in PLANETS:
            record = object_record(o)
            record.pop("materials", None)
            record["smoothing"] = [p.use_smooth for p in o.data.polygons]
            record["material_indices"] = [p.material_index for p in o.data.polygons]
            record["uv"] = {uv.name: [list(d.uv) for d in uv.data] for uv in o.data.uv_layers}
            record["modifiers"] = [(m.name, m.type, m.show_render, m.show_viewport) for m in o.modifiers]
            geometry[o.name] = digest(record)
        elif o.type == "CAMERA" and o.name not in CONFIG["cameras"]:
            cameras[o.name] = object_record(o)
    room = []
    for name in ("ARCHIVE_INTERIOR", "ROOM_LIGHTS"):
        for o in sorted(bpy.data.collections[name].all_objects, key=lambda v: v.name):
            row = object_record(o)
            if o.type == "MESH":
                row["assigned_materials"] = [s.material.name if s.material else None for s in o.material_slots]
            room.append(row)
    for name, value in hidden.items():
        bpy.data.collections[name].hide_viewport = value
    bpy.context.view_layer.update()
    materials = {m.name: digest(node_record(m)) for m in bpy.data.materials if not m.name.startswith(PREFIX)}
    return {"geometry": geometry, "cameras": cameras, "room": digest(room), "materials": materials}


def exterior_objects():
    protected = {o.name for o in bpy.data.collections["ARCHIVE_INTERIOR"].all_objects}
    for o in bpy.data.objects:
        if (o.type == "MESH" and o.name not in protected and not o.hide_render
                and all(not c.hide_render for c in o.users_collection)
                and all(c.name != "SPACE" for c in o.users_collection)):
            yield o


def clone_material(old):
    name = PREFIX + old.name
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    new = old.copy()
    new.name = name
    new["source_material"] = old.name
    return new


def recolor(material, color):
    nodes = material.node_tree.nodes
    nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1)
    ramp = nodes.get("Color Ramp")
    if not ramp or ramp.type != "VALTORGB":
        raise RuntimeError("Unexpected paint node layout: " + material.name)
    for i, element in enumerate(ramp.color_ramp.elements):
        element.color = (*(c * (.91 if i == 0 else 1.07) for c in color), 1)


def finishes():
    mapping, changed = {}, []
    for obj in exterior_objects():
        for slot in obj.material_slots:
            old = slot.material
            if not old:
                continue
            name = old.name
            coat = name.startswith(("BRIDGE02_paint_", "BRIDGE02_inspection_coating_"))
            if name not in CONFIG["paint"] and not coat and name != "STUDY_alloy":
                continue
            fresh = PREFIX + name not in bpy.data.materials
            new = clone_material(old)
            if fresh:
                if name == "STUDY_alloy":
                    recolor(new, (.38, .43, .46))
                    rough = new.node_tree.nodes.get("Map Range")
                    rough.inputs["To Min"].default_value = .26
                    rough.inputs["To Max"].default_value = .37
                else:
                    recolor(new, CONFIG["paint"]["SURFACE02_paint_0"] if coat else CONFIG["paint"][name])
                    # Existing chip mask still controls paint/primer/metal transitions.
                    shader = new.node_tree.nodes.get("Principled BSDF")
                    shader.inputs["Coat Weight"].default_value = .06
                    shader.inputs["Coat Roughness"].default_value = .38
                    if not coat:
                        rough = new.node_tree.nodes.get("Map Range")
                        rough.inputs["To Min"].default_value = .40
                        rough.inputs["To Max"].default_value = .51
            slot.link, slot.material = "OBJECT", new
            mapping[name] = new.name
            changed.append(obj.name)
    return {"mapping": mapping, "objects": sorted(set(changed))}


def cameras():
    base.COLLECTIONS.update({c.name: c for c in bpy.data.collections})
    for name, c in CONFIG["cameras"].items():
        obj = base.camera(name, c["position"], c["target"], lens=c["lens"])
        obj.rotation_euler = (obj.rotation_euler.to_quaternion() @ Quaternion((0, 0, 1), c.get("roll", 0))).to_euler()
        obj.data.clip_end = 100000000
    bpy.context.view_layer.update()


def planet_center():
    c, p = CONFIG["cameras"]["home"], CONFIG["planet"]
    forward = (Vector(c["target"]) - Vector(c["position"])).normalized()
    right = forward.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(forward)
    return (forward + right*p["right_offset"] + up*p["up_offset"]).normalized()*p["distance"]


def aim(obj, position, target=(0, 0, 0)):
    obj.location = position
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()


def environment(profile):
    scene = bpy.context.scene
    setting = CONFIG["profiles"][profile]
    direction = Vector(setting["stellar_direction"]).normalized()
    center = planet_center()
    for name, multiplier in zip(PLANETS, (1, 1.0025, 1.008)):
        o = bpy.data.objects[name]
        o.location, o.scale = center, (CONFIG["planet"]["radius"]*multiplier,)*3
        old = o.material_slots[0].material
        mat = clone_material(old)
        o.material_slots[0].link, o.material_slots[0].material = "OBJECT", mat
        if name == PLANETS[2]:
            for n in mat.node_tree.nodes:
                if n.type == "VECT_MATH" and n.operation == "SUBTRACT":
                    n.inputs[1].default_value = center
                elif n.type == "VECT_MATH" and n.operation == "DOT_PRODUCT":
                    n.inputs[1].default_value = direction
            o["stellar_direction"] = list(direction)
        elif name == PLANETS[1]:
            mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.24, .29, .32, 1)
    key = bpy.data.objects["ORBIT shared stellar key"]
    aim(key, direction*1000)
    key.data.energy, key.data.color, key.data.angle = setting["energy"], setting["color"], setting["angle"]
    planet_fill = bpy.data.objects["ORBIT planet-direction fill proxy"]
    aim(planet_fill, center.normalized()*1050)
    planet_fill.data.energy = setting["planet_fill_energy"]
    fill = bpy.data.objects["ORBIT low camera-side art fill"]
    aim(fill, (-480, -620, 310))
    fill.data.energy, fill.data.color, fill.data.size = setting["fill_energy"], setting["fill_color"], 650
    scene.view_settings.exposure = setting["exposure"]
    scene["home_profile"] = profile
    scene["fixed_home_planet_center"] = list(center)
    for node in scene.node_tree.nodes:
        if node.type == "GLARE":
            node.threshold, node.mix, node.size = 2.3, -.9, 7
    bpy.context.view_layer.update()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+"\n")


def build(args):
    if sha(args.scene) != CONFIG["input_sha256"]:
        raise SystemExit("Unexpected stern-study-01 source")
    target = args.output.resolve()/"flagship-home-look-01.blend"
    if target.exists() and not args.overwrite:
        raise SystemExit("Output exists; use another directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    before = snapshot()
    mapping = finishes()
    cameras()
    if args.profile != "materials":
        environment(args.profile)
    scene = bpy.context.scene
    scene.name, scene["revision"] = "KUHAI — Home Look 01", CONFIG["revision"]
    scene.camera, scene.render.filepath = bpy.data.objects["home"], "//previews/home.png"
    scene["home_profile"] = args.profile
    if snapshot() != before:
        raise RuntimeError("Protected geometry, archive, cameras or original materials changed")
    texture_dir = target.parent/"textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    for image in bpy.data.images:
        if image.type == "IMAGE" and image.users:
            if not image.packed_file:
                raise RuntimeError("Missing packed resource")
            name = Path(image.filepath).name
            (texture_dir/name).write_bytes(image.packed_file.data)
            image.filepath = "//textures/"+name
            for packed in image.packed_files:
                packed.filepath = image.filepath
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=True, relative_remap=False)
    write_json(target.parent/"look-manifest.json", {**CONFIG, "profile": args.profile, **mapping,
               "source_sha256": sha(target), "source_bytes": target.stat().st_size, "blender": bpy.app.version_string})
    print("HOME_BUILD", args.profile, len(mapping["objects"]), sha(target), flush=True)


def bounds(scene, camera):
    points = []
    for obj in exterior_objects():
        for point in obj.bound_box:
            points.append(world_to_camera_view(scene, camera, obj.matrix_world@Vector(point)))
    return {"min": [min(p[i] for p in points) for i in range(3)],
            "max": [max(p[i] for p in points) for i in range(3)]}


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    if "home" not in bpy.data.objects:
        cameras()
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.threads_mode, scene.render.threads = "FIXED", 6
    scene.cycles.samples, scene.cycles.use_adaptive_sampling = args.samples, False
    devices = select_device(scene, args.device)
    args.output.mkdir(parents=True, exist_ok=True)
    record = {"revision": CONFIG["revision"], "profile": scene.get("home_profile", "baseline"),
              "source_sha256": sha(args.scene), "width": args.width, "height": args.height,
              "samples": args.samples, "device": args.device, "devices": devices, "threads": 6, "renders": []}
    for name in args.views.split(","):
        path = args.output.resolve()/(name+".png")
        if path.exists() and not args.overwrite:
            raise SystemExit("Render exists")
        camera = bpy.data.objects.get(name)
        if not camera or camera.type != "CAMERA":
            raise SystemExit("Unknown camera: "+name)
        scene.camera, scene.render.filepath = camera, str(path)
        bpy.context.view_layer.update()
        framing = bounds(scene, camera)
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["renders"].append({"view": name, "seconds": round(time.perf_counter()-start, 3),
                                  "peak_process_rss_mib": peak_process_rss_mib(), "ship_projected_bounds": framing})
        write_json(args.output/"benchmark.json", record)
        print("HOME_RENDER "+json.dumps(record["renders"][-1]), flush=True)


def inspect(args):
    if sha(args.baseline) != CONFIG["input_sha256"]:
        raise SystemExit("Wrong baseline")
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    before = snapshot()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    after = snapshot()
    checks = {key+"_preserved": before[key] == after[key] for key in before}
    source = bpy.data.objects["ORBIT shared stellar key"]
    direction = (source.matrix_world.to_quaternion()@Vector((0, 0, 1))).normalized()
    atmosphere = bpy.data.objects[PLANETS[2]]
    nodes = atmosphere.material_slots[0].material.node_tree.nodes
    shader_direction = next(n.inputs[1].default_value for n in nodes if n.type == "VECT_MATH" and n.operation == "DOT_PRODUCT")
    center = next(n.inputs[1].default_value for n in nodes if n.type == "VECT_MATH" and n.operation == "SUBTRACT")
    checks["star_and_atmosphere_direction_agree"] = (direction-Vector(shader_direction)).length < 1e-5
    checks["planet_and_limb_center_agree"] = (atmosphere.location-Vector(center)).length < 1
    checks["planet_shells_concentric"] = all(
        (bpy.data.objects[n].location-atmosphere.location).length < 1
        and abs(bpy.data.objects[n].scale.x-CONFIG["planet"]["radius"]*factor) < 1
        for n, factor in zip(PLANETS, (1, 1.0025, 1.008)))
    images = []
    for img in bpy.data.images:
        if img.type == "IMAGE" and img.users:
            local = Path(bpy.path.abspath(img.filepath))
            valid = bool(img.packed_file) and img.filepath.startswith("//") and local.is_file()
            valid = valid and hashlib.sha256(img.packed_file.data).hexdigest() == sha(local)
            images.append({"name": img.name, "path": img.filepath, "packed_matches_relative_file": bool(valid)})
    checks["images_portable"] = all(v["packed_matches_relative_file"] for v in images)
    checks["no_animation_added"] = all(bpy.data.objects[n].animation_data is None for n in CONFIG["cameras"])
    record = {"revision": CONFIG["revision"], "profile": bpy.context.scene.get("home_profile"),
              "input_sha256": sha(args.baseline), "source_sha256": sha(args.scene), "checks": checks,
              "original_meshes": len(before["geometry"]), "original_materials": len(before["materials"]),
              "images": images, "passed": all(checks.values()), "browser_tested": False}
    write_json(args.output, record)
    print(json.dumps(record, indent=2))
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "render", "inspect"):
        p = sub.add_parser(command)
        p.add_argument("--scene", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--overwrite", action="store_true")
        if command == "build":
            p.add_argument("--profile", choices=("day", "rim", "materials"), default=CONFIG["selected_profile"])
        if command == "inspect":
            p.add_argument("--baseline", type=Path, required=True)
        if command == "render":
            p.add_argument("--views", default="home")
            p.add_argument("--width", type=int, default=960)
            p.add_argument("--height", type=int, default=600)
            p.add_argument("--samples", type=int, default=32)
            p.add_argument("--device", choices=("cpu", "optix"), default="cpu")
    args = parser.parse_args(argv)
    if args.command == "render" and not (64 <= args.width <= 4096 and 64 <= args.height <= 4096 and 1 <= args.samples <= 1024):
        raise SystemExit("Invalid preview size")
    {"build": build, "render": render, "inspect": inspect}[args.command](args)
