"""Bake one paint swatch on CPU and export a separate, embedded-texture GLB.

This is a 2.5 m material tile, not the detailed shoulder's web mesh. It verifies
the material conversion route without assuming visitor GPUs can run Cycles.
python bake_material_swatch.py --scene shoulder-material-study.blend --output web-swatch
"""

import argparse
import json
import struct
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from render_study import peak_process_rss_mib


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--overwrite", action="store_true")
    a = parser.parse_args(argv)
    if a.size not in (256, 512, 1024, 2048):
        raise SystemExit("Choose a bounded sample size: 256, 512, 1024 or 2048")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "armor-material-swatch.glb").exists() and not a.overwrite:
        raise SystemExit("Sample already exists; use another directory or --overwrite")
    texdir = out / "textures"
    texdir.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene = bpy.data.scenes.new("KUHAI — Baked Armor Material Sample")
    bpy.context.window.scene = scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.max_bounces = 4
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 6
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = True
    scene.render.bake.normal_space = "TANGENT"
    bpy.ops.mesh.primitive_plane_add(size=2.5)
    plane = bpy.context.object
    plane.name = "2.5 m paint swatch - not ship geometry"
    plane["role"] = "material_swatch"
    source = bpy.data.materials["STUDY_naval_paint"].copy()
    source.name = "SOURCE_paint_swatch"
    plane.data.materials.append(source)
    nodes, links = source.node_tree.nodes, source.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    surface_output = nodes.get("Material Output").inputs["Surface"]
    emission = nodes.new("ShaderNodeEmission")
    target = nodes.new("ShaderNodeTexImage")
    target.label = "Active bake target only"
    record = {"kind": "Paint material conversion sample, not a web-ready flagship", "size": a.size,
              "tile_width_m": 2.5, "device": "CPU", "threads": 6, "bake_samples": 8,
              "blender": bpy.app.version_string, "maps": {}, "timings": [],
              "ao": "Constant 1; no baked occlusion claimed", "browser_performance_tested": False}

    def bake(name, kind, color_space, socket=None):
        image = bpy.data.images.new(name, width=a.size, height=a.size, alpha=False)
        image.colorspace_settings.name = color_space
        target.image = image
        for node in nodes:
            node.select = False
        target.select = True
        nodes.active = target
        if socket is not None:
            for link in list(emission.inputs["Color"].links):
                links.remove(link)
            if socket.is_linked:
                links.new(socket.links[0].from_socket, emission.inputs["Color"])
            else:
                value = socket.default_value
                emission.inputs["Color"].default_value = (value, value, value, 1) if isinstance(value, float) else value
            links.new(emission.outputs[0], surface_output)
        else:
            links.new(bsdf.outputs[0], surface_output)
        start = time.perf_counter()
        bpy.ops.object.bake(type=kind)
        record["timings"].append({"operation": name, "seconds": round(time.perf_counter() - start, 3)})
        image.filepath_raw = str(texdir / (name + ".png"))
        image.file_format = "PNG"
        image.save()
        record["maps"][name] = {"path": "textures/" + name + ".png", "colorspace": color_space,
                                 "bytes": Path(image.filepath_raw).stat().st_size}
        print("SWATCH_BAKE " + json.dumps(record["timings"][-1]), flush=True)
        return image

    color = bake("armor-color", "EMIT", "sRGB", bsdf.inputs["Base Color"])
    rough = bake("armor-roughness", "EMIT", "Non-Color", bsdf.inputs["Roughness"])
    normal = bake("armor-normal", "NORMAL", "Non-Color")
    links.new(bsdf.outputs[0], surface_output)
    nodes.remove(target)
    nodes.remove(emission)
    values = np.asarray(rough.pixels[:], dtype=np.float32).reshape(-1, 4)
    packed = np.ones_like(values)
    packed[:, 1] = values[:, 0]
    packed[:, 2] = 0  # Dielectric paint. Exposed metal is separate source geometry.
    orm = bpy.data.images.new("armor-orm", width=a.size, height=a.size, alpha=False)
    orm.colorspace_settings.name = "Non-Color"
    orm.pixels.foreach_set(packed.ravel())
    orm.filepath_raw = str(texdir / "armor-orm.png")
    orm.file_format = "PNG"
    orm.save()
    record["maps"]["armor-orm"] = {"path": "textures/armor-orm.png", "colorspace": "Non-Color",
                                   "channels": "R=1 (unused AO), G=roughness, B=0 (paint metalness)",
                                   "bytes": Path(orm.filepath_raw).stat().st_size}
    record["roughness_range"] = [float(values[:, 0].min()), float(values[:, 0].max())]
    material = bpy.data.materials.new("WEB_baked_naval_paint")
    material.use_nodes = True
    n, l = material.node_tree.nodes, material.node_tree.links
    shader = n.get("Principled BSDF")
    maps = {}
    for name, img in (("base", color), ("orm", orm), ("normal", normal)):
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
    plane.data.materials[0] = material
    path = out / "armor-material-swatch.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True,
                              export_extras=True, export_cameras=False, export_lights=False,
                              export_animations=False, export_yup=True)
    data = path.read_bytes()
    length = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + length])
    mat = doc["materials"][0]
    record["glb"] = {"bytes": len(data), "meshes": len(doc["meshes"]), "materials": len(doc["materials"]),
                     "images": len(doc["images"]),
                     "triangles": sum(doc["accessors"][p["indices"]]["count"] // 3 for m in doc["meshes"] for p in m["primitives"])}
    record["checks"] = {
        "images_embedded": all("bufferView" in img and "uri" not in img for img in doc["images"]),
        "no_external_buffers": all("uri" not in b for b in doc["buffers"]),
        "base_color_texture": "baseColorTexture" in mat["pbrMetallicRoughness"],
        "metallic_roughness_texture": "metallicRoughnessTexture" in mat["pbrMetallicRoughness"],
        "normal_texture": "normalTexture" in mat,
        "uv_present": all("TEXCOORD_0" in p["attributes"] for m in doc["meshes"] for p in m["primitives"]),
        "roughness_valid_nonconstant": 0 <= values[:, 0].min() < values[:, 0].max() <= 1,
    }
    record["checks"] = {k: bool(v) for k, v in record["checks"].items()}
    # Same geometry/camera/lights, changing only the shader; this is a Blender
    # source-vs-baked appearance check, not a browser rendering test.
    scene.world = bpy.data.worlds.new("Swatch neutral ambience")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.10, .10, .10, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .2
    camera_data = bpy.data.cameras.new("swatch")
    camera = bpy.data.objects.new("swatch", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0, -1.7, 4.5)
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 3.2
    scene.camera = camera
    lamp_data = bpy.data.lights.new("Swatch broad key", "AREA")
    lamp_data.energy = 350
    lamp_data.shape = "DISK"
    lamp_data.size = 3
    lamp = bpy.data.objects.new(lamp_data.name, lamp_data)
    scene.collection.objects.link(lamp)
    lamp.location = (-1, -1, 3)
    lamp.rotation_euler = (-lamp.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.cycles.samples = 24
    for name, mat in (("swatch-source", source), ("swatch-baked", material)):
        plane.data.materials[0] = mat
        scene.render.filepath = str(out / (name + ".png"))
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["timings"].append({"operation": name, "seconds": round(time.perf_counter() - start, 3)})
    # Read the actual GLB back through Blender's independent importer, rather
    # than assuming the material graph survived the exporter unchanged.
    plane.hide_render = True
    before_import = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in set(bpy.data.objects) - before_import if o.type == "MESH"]
    record["checks"]["glb_imports_as_one_mesh"] = len(imported) == 1
    scene.render.filepath = str(out / "swatch-glb.png")
    start = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    record["timings"].append({"operation": "swatch-glb-roundtrip", "seconds": round(time.perf_counter() - start, 3)})
    record["peak_process_rss_mib"] = peak_process_rss_mib()
    record["passed"] = all(record["checks"].values())
    (out / "bake-report.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print("SWATCH_RESULT " + json.dumps(record, ensure_ascii=False), flush=True)
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
