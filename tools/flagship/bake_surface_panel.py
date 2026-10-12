"""Bake the actual surface-study-02 maintenance cover with CPU-only defaults.

The GLB contains one existing beveled cover, not its fasteners or the whole
ship. It preserves source-world meters and embeds all web material textures.
"""
import argparse
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_study import peak_process_rss_mib

OBJECT = "SURFACE02 / Archive maintenance cover"


def main():
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, choices=(256, 512, 1024, 2048), default=1024)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    out = args.output.resolve()
    path = out / "archive-maintenance-cover.glb"
    if path.exists() and not args.overwrite:
        raise SystemExit("Output exists; choose another directory")
    texdir = out / "textures"
    texdir.mkdir(parents=True, exist_ok=True)
    input_sha = hashlib.sha256(args.scene.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    original = bpy.data.objects[OBJECT]
    world_matrix = original.matrix_world.copy()
    evaluated = original.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True,
                                         depsgraph=bpy.context.evaluated_depsgraph_get())
    material_source = original.active_material.copy()
    material_source.name = "SOURCE_maintenance_cover"
    scene = bpy.data.scenes.new("KUHAI — Actual Maintenance Cover Material Bake")
    bpy.context.window.scene = scene
    cover = bpy.data.objects.new("Archive maintenance cover — existing evaluated mesh", mesh)
    scene.collection.objects.link(cover)
    cover.matrix_world = world_matrix
    cover["source_object"] = OBJECT
    cover["source_revision"] = "surface-study-02"
    cover["units"] = "Meters, original ship-world position; glTF uses Y up"
    cover.data.materials.clear()
    cover.data.materials.append(material_source)
    cover.select_set(True)
    bpy.context.view_layer.objects.active = cover
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.035)
    bpy.ops.object.mode_set(mode="OBJECT")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.max_bounces = 4
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = False
    scene.render.threads_mode, scene.render.threads = "FIXED", 6
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = True
    scene.render.bake.normal_space = "TANGENT"
    record = {"revision": "surface-study-02", "source_sha256": input_sha,
              "source_object": OBJECT, "scope": "Cover only, excludes separate locks and fasteners",
              "dimensions_m": [round(v, 5) for v in original.dimensions],
              "original_position_m": list(world_matrix.translation),
              "units": "1 glTF unit = 1 meter; existing review ship uses a separate 100m/unit convention",
              "device": "CPU", "threads": 6, "bake_samples": 8, "texture_size": args.size,
              "blender": bpy.app.version_string, "maps": {}, "timings": [],
              "ao": "R is constant 1, not baked occlusion", "browser_performance_tested": False}
    nodes, links = material_source.node_tree.nodes, material_source.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    output = nodes.get("Material Output").inputs["Surface"]
    emission, target = nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeTexImage")

    def bake(name, kind, space, socket=None):
        image = bpy.data.images.new(name, width=args.size, height=args.size, alpha=False)
        image.colorspace_settings.name = space
        target.image = image
        for node in nodes:
            node.select = False
        target.select = True
        nodes.active = target
        if socket is None:
            links.new(bsdf.outputs[0], output)
        else:
            for link in list(emission.inputs["Color"].links):
                links.remove(link)
            if socket.is_linked:
                links.new(socket.links[0].from_socket, emission.inputs["Color"])
            else:
                value = socket.default_value
                emission.inputs["Color"].default_value = (value,value,value,1) if isinstance(value,float) else value
            links.new(emission.outputs[0], output)
        start = time.perf_counter()
        bpy.ops.object.bake(type=kind)
        record["timings"].append({"operation": name, "seconds": round(time.perf_counter()-start,3)})
        image.filepath_raw = str(texdir / (name + ".png"))
        image.file_format = "PNG"
        image.save()
        record["maps"][name] = {"path": "textures/"+name+".png", "color_space": space,
                                 "bytes": Path(image.filepath_raw).stat().st_size}
        print("COVER_BAKE " + json.dumps(record["timings"][-1]), flush=True)
        return image

    color = bake("cover-color", "EMIT", "sRGB", bsdf.inputs["Base Color"])
    rough = bake("cover-roughness", "EMIT", "Non-Color", bsdf.inputs["Roughness"])
    normal = bake("cover-normal", "NORMAL", "Non-Color")
    links.new(bsdf.outputs[0], output)
    nodes.remove(target)
    nodes.remove(emission)
    values = np.asarray(rough.pixels[:], dtype=np.float32).reshape(-1,4)
    packed = np.ones_like(values)
    packed[:,1], packed[:,2] = values[:,0], 0
    orm = bpy.data.images.new("cover-orm", width=args.size, height=args.size, alpha=False)
    orm.colorspace_settings.name = "Non-Color"
    orm.pixels.foreach_set(packed.ravel())
    orm.filepath_raw, orm.file_format = str(texdir / "cover-orm.png"), "PNG"
    orm.save()
    record["maps"]["cover-orm"] = {"path": "textures/cover-orm.png", "color_space": "Non-Color",
                                   "channels": "R=1 (unused AO), G=roughness, B=0 (dielectric paint)",
                                   "bytes": Path(orm.filepath_raw).stat().st_size}
    material = bpy.data.materials.new("WEB_maintenance_cover_paint")
    material.use_nodes = True
    n, l = material.node_tree.nodes, material.node_tree.links
    shader = n.get("Principled BSDF")
    maps = {}
    for name,img in (("base",color),("orm",orm),("normal",normal)):
        node = n.new("ShaderNodeTexImage")
        node.image = img
        maps[name] = node
    l.new(maps["base"].outputs["Color"], shader.inputs["Base Color"])
    separate = n.new("ShaderNodeSeparateColor")
    separate.mode = "RGB"
    l.new(maps["orm"].outputs["Color"], separate.inputs[0])
    l.new(separate.outputs["Green"], shader.inputs["Roughness"])
    l.new(separate.outputs["Blue"], shader.inputs["Metallic"])
    normal_map = n.new("ShaderNodeNormalMap")
    l.new(maps["normal"].outputs["Color"], normal_map.inputs["Color"])
    l.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    cover.data.materials[0] = material
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True,
                              export_extras=True, export_cameras=False, export_lights=False,
                              export_animations=False, export_yup=True, export_tangents=True)
    data = path.read_bytes()
    length = struct.unpack("<I",data[12:16])[0]
    doc = json.loads(data[20:20+length])
    mat = doc["materials"][0]
    record["glb"] = {"bytes":len(data), "sha256":hashlib.sha256(data).hexdigest(),
                     "meshes":len(doc["meshes"]), "images":len(doc["images"]),
                     "triangles":sum(doc["accessors"][p["indices"]]["count"]//3 for m in doc["meshes"] for p in m["primitives"])}
    record["checks"] = {
        "one_actual_source_mesh":len(doc["meshes"]) == 1,
        "images_embedded":all("bufferView" in i and "uri" not in i for i in doc["images"]),
        "no_external_buffers":all("uri" not in b for b in doc["buffers"]),
        "base_color_texture":"baseColorTexture" in mat["pbrMetallicRoughness"],
        "metallic_roughness_texture":"metallicRoughnessTexture" in mat["pbrMetallicRoughness"],
        "normal_texture":"normalTexture" in mat,
        "uv_and_tangent_present":all(all(a in p["attributes"] for a in ("TEXCOORD_0","TANGENT")) for m in doc["meshes"] for p in m["primitives"]),
        "roughness_valid_nonconstant":bool(0 <= values[:,0].min() < values[:,0].max() <= 1),
    }
    # Matched render of the procedural source, the baked shader, and an actual
    # GLB importer round trip. No source save or production site mutation.
    scene.world = bpy.data.worlds.new("Cover neutral ambience")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.10,.10,.10,1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .35
    center = world_matrix.translation
    camera_data = bpy.data.cameras.new("cover")
    camera = bpy.data.objects.new("cover",camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((2,-4,5.5))
    camera.rotation_euler = (center-camera.location).to_track_quat("-Z","Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", 5.8
    scene.camera = camera
    lamp_data = bpy.data.lights.new("Cover broad key","AREA")
    lamp_data.energy, lamp_data.shape, lamp_data.size = 900, "DISK", 5
    lamp = bpy.data.objects.new(lamp_data.name,lamp_data)
    scene.collection.objects.link(lamp)
    lamp.location = center + Vector((-1,-2,5))
    lamp.rotation_euler = (center-lamp.location).to_track_quat("-Z","Y").to_euler()
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.cycles.samples = 24

    def render(name):
        scene.render.filepath = str(out / (name+".png"))
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["timings"].append({"operation":name,"seconds":round(time.perf_counter()-start,3)})

    for name,mat in (("cover-source",material_source),("cover-baked",material)):
        cover.data.materials[0] = mat
        render(name)
    cover.hide_render = True
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in set(bpy.data.objects)-before if o.type == "MESH"]
    record["checks"]["glb_imports_as_one_mesh"] = len(imported) == 1
    render("cover-glb-roundtrip")
    record["checks"]["source_file_unchanged"] = hashlib.sha256(args.scene.read_bytes()).hexdigest() == input_sha
    record["peak_process_rss_mib"] = peak_process_rss_mib()
    record["passed"] = all(record["checks"].values())
    (out / "bake-report.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    print("COVER_RESULT " + json.dumps(record,ensure_ascii=False),flush=True)
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
