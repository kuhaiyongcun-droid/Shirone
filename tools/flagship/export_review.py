"""Derive a merged web study from form-study-03, without writing the input blend.

Run with the same bpy 4.5.14 environment as the source. Coordinates are divided
by 100 before glTF's Z-up -> Y-up conversion. Only selected ship meshes export.
Procedural paint is deliberately approximated by simple PBR, not baked.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import bpy

SOURCE_SHA = "126e2b183a39a34ba1c4113e190358cf7b0d3f48d36802a28f4f5359d8092259"
GROUPS = {
    "SHIP_HULL": "hull", "PORT_DETAILS": "hull", "STARBOARD_DETAILS": "hull",
    "ARCHIVE_SHELL": "archive_shell", "ARCHIVE_INTERIOR": "archive_interior",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(source, output):
    before = digest(source)
    if before != SOURCE_SHA:
        raise ValueError("Expected the approved form-study-03 source fingerprint")
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    for name in GROUPS:
        collection = bpy.data.collections[name]
        collection.hide_viewport = collection.hide_render = False
        for obj in collection.objects:
            obj.hide_set(False)
            # Web-only reduction. High precision source and its modifiers are untouched.
            for modifier in obj.modifiers:
                if modifier.type == "BEVEL":
                    modifier.segments = 1
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    batches = {}
    vertex_maps = {}
    skipped_degenerate = 0
    for group, role in GROUPS.items():
        for obj in bpy.data.collections[group].objects:
            if obj.type != "MESH":
                continue
            evaluated = obj.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
            for tri in mesh.loop_triangles:
                material = mesh.materials[tri.material_index]
                points = [(obj.matrix_world @ mesh.vertices[i].co) / 100 for i in tri.vertices]
                face_normal = (points[1] - points[0]).cross(points[2] - points[0])
                longest = max((points[i] - points[(i + 1) % 3]).length for i in range(3))
                # Remove numerical slivers below 0.1 mm source altitude before
                # Draco quantization, preserving stable normals on tiny details.
                if longest == 0 or face_normal.length / longest < 1e-6:
                    skipped_degenerate += 1
                    continue
                face_normal.normalize()
                key = (role, material.name)
                vertices, faces, normals = batches.setdefault(key, ([], [], []))
                lookup = vertex_maps.setdefault(key, {})
                indices = []
                for point in points:
                    value = tuple(point)
                    if value not in lookup:
                        lookup[value] = len(vertices)
                        vertices.append(value)
                    indices.append(lookup[value])
                faces.append(tuple(indices))
                for i in tri.loops:
                    normal = normal_matrix @ mesh.corner_normals[i].vector
                    normals.append(tuple(normal.normalized() if normal.length > .5 else face_normal))
            evaluated.to_mesh_clear()

    material_cache = {}
    files = {}
    for filename, roles in (("flagship.glb", {"hull", "archive_shell"}),
                            ("archive.glb", {"archive_interior"})):
        scene = bpy.data.scenes.new(filename)
        bpy.context.window.scene = scene
        count, triangles = 0, 0
        for (role, name), (vertices, faces, normals) in batches.items():
            if role not in roles:
                continue
            if name not in material_cache:
                original = bpy.data.materials[name]
                material = bpy.data.materials.new("WEB_" + name)
                material.use_nodes = True
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Base Color"].default_value = original.diffuse_color
                bsdf.inputs["Metallic"].default_value = original.get("web_metallic", 0)
                bsdf.inputs["Roughness"].default_value = original.get("web_roughness", .6)
                bsdf.inputs["Emission Color"].default_value = original.diffuse_color
                bsdf.inputs["Emission Strength"].default_value = min(original.get("web_emission", 0), 2.8)
                material_cache[name] = material
            mesh = bpy.data.meshes.new(role + "__" + name)
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            for poly in mesh.polygons:
                poly.use_smooth = True
            mesh.normals_split_custom_set(normals)
            mesh.materials.append(material_cache[name])
            obj = bpy.data.objects.new(mesh.name, mesh)
            obj["role"] = role
            if role.startswith("archive"):
                obj["room_id"] = "archive"
            scene.collection.objects.link(obj)
            count += 1
            triangles += len(faces)
        path = output / filename
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True,
                                 export_extras=True, export_cameras=False, export_lights=False,
                                 export_animations=False, export_apply=True, export_yup=True,
                                 export_draco_mesh_compression_enable=True,
                                 export_draco_mesh_compression_level=6,
                                 export_draco_position_quantization=20,
                                 export_draco_normal_quantization=10)
        data = path.read_bytes()
        document = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
        final_triangles = sum(document["accessors"][p["indices"]]["count"] // 3
                              for m in document["meshes"] for p in m["primitives"])
        # Draco also removes coincident duplicate faces; count the actual file.
        files[filename] = {"batches": count, "triangles": final_triangles,
                           "triangles_before_encoding": triangles, "bytes": path.stat().st_size,
                           "sha256": digest(path)}
    assert digest(source) == before
    report = {"revision": "review-study-01", "source_revision": "form-study-03",
              "source_sha256": before, "blender": bpy.app.version_string,
              "units": "100 source meters per web unit; Y-up, bow -X, port +Z",
              "files": files, "source_file_unchanged": True,
              "materials": "Simple untextured PBR; procedural paint and roughness not baked",
              "compression": "KHR_draco_mesh_compression; position 20 bits, normal 10 bits; local decoder",
              "degenerate_source_triangles_removed": skipped_degenerate,
              "archive_anchor": [-.80, .30, .48],
              "browser_performance_tested": False}
    (output / "model-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
