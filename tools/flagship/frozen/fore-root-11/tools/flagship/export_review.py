"""Derive a merged web study from a known source, without writing its blend.

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

SOURCE_REVISIONS = {
    "126e2b183a39a34ba1c4113e190358cf7b0d3f48d36802a28f4f5359d8092259": "form-study-03",
    "e05803fd34da6ccff0fb680bf3953165aabf742bd659342f5680de1022d0e9a7": "home-look-01",
    "14a58708c990193d989f298f3f628b5a89dc7b2b82c476281630187a5494d57a": "side-study-03",
}
GROUPS = {
    "SHIP_HULL": "hull", "PORT_DETAILS": "hull", "STARBOARD_DETAILS": "hull",
    "ARCHIVE_SHELL": "archive_shell", "ARCHIVE_INTERIOR": "archive_interior",
    "SURFACE03_HULL": "hull", "BRIDGE01_EXTERIOR": "hull",
    "BRIDGE02_DETAILS": "hull", "STERN01_DETAILS": "hull",
    "SIDE03_STRUCTURE": "hull",
}


def visible_objects(collection):
    if collection.hide_render:
        return
    collection.hide_viewport = False
    for obj in collection.objects:
        if not obj.hide_render and obj.type == "MESH":
            obj.hide_set(False)
            yield obj
    for child in collection.children:
        yield from visible_objects(child)


def simple_pbr(original):
    """Sample explicit source defaults, honoring HOME01 object overrides.

    Linked procedural colors and wear masks remain an unbaked approximation.
    """
    shader = original.node_tree.nodes.get("Principled BSDF") if original.use_nodes else None
    color = tuple(shader.inputs["Base Color"].default_value) if shader else tuple(original.diffuse_color)
    metallic = shader.inputs["Metallic"].default_value if shader else original.get("web_metallic", 0)
    roughness = shader.inputs["Roughness"].default_value if shader else original.get("web_roughness", .6)
    rough = original.node_tree.nodes.get("Map Range") if shader else None
    if rough and rough.type == "MAP_RANGE" and rough.inputs["To Min"].default_value > 0:
        roughness = (rough.inputs["To Min"].default_value + rough.inputs["To Max"].default_value) / 2
    emission_color = tuple(shader.inputs["Emission Color"].default_value) if shader else color
    emission = shader.inputs["Emission Strength"].default_value if shader else original.get("web_emission", 0)
    return color, metallic, roughness, emission_color, min(emission, 2.8)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(source, output):
    before = digest(source)
    if before not in SOURCE_REVISIONS:
        raise ValueError("Unexpected source fingerprint; use a registered immutable scene")
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    objects = {}
    for name, role in GROUPS.items():
        collection = bpy.data.collections.get(name)
        if not collection:
            continue
        for obj in visible_objects(collection):
            objects[obj.name] = (obj, role)
            # Web-only reduction. High precision source and its modifiers are untouched.
            for modifier in obj.modifiers:
                if modifier.type == "BEVEL":
                    modifier.segments = 1
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    batches = {}
    vertex_maps = {}
    skipped_degenerate = 0
    for obj, role in objects.values():
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for tri in mesh.loop_triangles:
            material = obj.material_slots[tri.material_index].material
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
            vertices, faces, normals, uvs = batches.setdefault(key, ([], [], [], []))
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
                uvs.append(tuple(mesh.uv_layers.active.data[i].uv) if mesh.uv_layers.active else (0,0))
        evaluated.to_mesh_clear()

    material_cache = {}
    files = {}
    for filename, roles in (("flagship.glb", {"hull", "archive_shell"}),
                            ("archive.glb", {"archive_interior"})):
        scene = bpy.data.scenes.new(filename)
        bpy.context.window.scene = scene
        count, triangles = 0, 0
        for (role, name), (vertices, faces, normals, uvs) in batches.items():
            if role not in roles:
                continue
            if name not in material_cache:
                original = bpy.data.materials[name]
                material = original.copy() if original.get('baked_pbr') else bpy.data.materials.new("WEB_" + name)
                material.name="WEB_"+name
                material.use_nodes = True
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                color, metallic, roughness, glow_color, glow = simple_pbr(original)
                if not original.get('baked_pbr'):
                    bsdf.inputs["Base Color"].default_value = color
                    bsdf.inputs["Metallic"].default_value = metallic
                    bsdf.inputs["Roughness"].default_value = roughness
                bsdf.inputs["Emission Color"].default_value = glow_color
                bsdf.inputs["Emission Strength"].default_value = glow
                material_cache[name] = material
            mesh = bpy.data.meshes.new(role + "__" + name)
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            for poly in mesh.polygons:
                poly.use_smooth = True
            mesh.normals_split_custom_set(normals)
            if bpy.data.materials[name].get('baked_pbr'):
                uv=mesh.uv_layers.new(name='SurfaceAtlas')
                for loop,value in zip(uv.data,uvs):loop.uv=value
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
                                 export_draco_texcoord_quantization=16,
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
    report = {"revision": "review-study-03", "source_revision": SOURCE_REVISIONS[before],
              "source_sha256": before, "blender": bpy.app.version_string,
              "units": "100 source meters per web unit; Y-up, bow -X, port +Z",
              "files": files, "source_file_unchanged": True,
              "materials": "Simple untextured PBR; procedural paint and roughness not baked",
              "compression": "KHR_draco_mesh_compression; position 20 bits, normal 10 bits; local decoder",
              "degenerate_source_triangles_removed": skipped_degenerate,
              "visible_source_objects": len(objects),
              "object_material_overrides_respected": True,
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

