"""Validate a relocated .blend and inspect the companion GLB without external assets.

blender -b --python inspect_scene.py -- --scene ./output/flagship-blockout.blend
python inspect_scene.py --scene ./output/flagship-blockout.blend

Checks: reopenability, external resource closure, room geometry bounds, named shell
separation, static hull/cameras during a shell toggle, and exported GLB semantics.
This does not claim browser rendering, final art, collision-free walkability or FPS.
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def comparison_signatures():
    """Hash comparable source data, excluding revision names and export meshes."""
    def checksum(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    groups = {}
    for name in ("CAMERAS", "LIGHTING", "ARCHIVE_INTERIOR"):
        values = []
        for ob in sorted(bpy.data.collections[name].objects, key=lambda obj: obj.name):
            row = {"name": ob.name, "matrix": list(map(list, ob.matrix_world))}
            if ob.type == "CAMERA":
                row.update(type=ob.data.type, lens=ob.data.lens, ortho=ob.data.ortho_scale)
            elif ob.type == "LIGHT":
                row.update(type=ob.data.type, energy=ob.data.energy, color=list(ob.data.color))
                row["extent"] = ob.data.size if ob.data.type == "AREA" else ob.data.angle
            elif ob.type == "MESH":
                row.update(vertices=[list(v.co) for v in ob.data.vertices],
                           # Blender may emit the same UV-sphere faces in a
                           # different order; face order is not a shape change.
                           faces=sorted(list(p.vertices) for p in ob.data.polygons),
                           materials=[m.name for m in ob.data.materials])
            values.append(row)
        groups[name] = checksum(values)
    return groups


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path, help="Optional previous .blend for camera/light/interior comparison")
    args = parser.parse_args(argv)
    source = args.scene.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = next(s for s in bpy.data.scenes if s.name.startswith("KUHAI"))
    bpy.context.window.scene = scene
    checks = {}
    external_images = [i.filepath for i in bpy.data.images if i.source == "FILE" and not i.packed_file]
    external_libraries = [l.filepath for l in bpy.data.libraries]
    checks["no_unpacked_external_images"] = not external_images
    checks["no_linked_blend_libraries"] = not external_libraries
    checks["render_path_is_relative"] = scene.render.filepath.startswith("//")
    shell = bpy.data.collections["ARCHIVE_SHELL"]
    interior = bpy.data.collections["ARCHIVE_INTERIOR"]
    hull = bpy.data.collections["SHIP_HULL"]
    checks["archive_shell_independent"] = not (set(shell.objects) & set(interior.objects) or set(shell.objects) & set(hull.objects))
    cameras_before = {o.name: list(map(list, o.matrix_world)) for o in bpy.data.collections["CAMERAS"].objects}
    hull_before = {o.name: list(map(list, o.matrix_world)) for o in hull.objects}
    shell.hide_render = True
    shell.hide_viewport = True
    bpy.context.view_layer.update()
    checks["cutaway_keeps_camera_transforms"] = cameras_before == {o.name: list(map(list, o.matrix_world)) for o in bpy.data.collections["CAMERAS"].objects}
    checks["cutaway_keeps_hull_transforms"] = hull_before == {o.name: list(map(list, o.matrix_world)) for o in hull.objects}
    # Archive furnishings fit inside the reserved bay (not an entire-deck floor plan).
    bounds = [(-114, -53, 16.5), (-46, -21, 26.5)]
    escaped = []
    for obj in interior.objects:
        for corner in obj.bound_box:
            position = obj.matrix_world @ Vector(corner)
            if any(not (bounds[0][i] - 0.05 <= position[i] <= bounds[1][i] + 0.05) for i in range(3)):
                escaped.append(obj.name)
                break
    checks["archive_inside_reserved_bay"] = not escaped
    # Closed source volumes catch flipped lofts or missing end caps. Overlapping
    # armor assemblies are intentional; this is not an intersection/physics test.
    invalid_meshes = []
    for obj in hull.objects:
        if obj.type != "MESH":
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        if not all(edge.is_manifold for edge in mesh.edges) or mesh.calc_volume(signed=True) <= 0:
            invalid_meshes.append(obj.name)
        mesh.free()
    checks["hull_source_volumes_closed_outward"] = not invalid_meshes
    glb = source.with_name("flagship-web-study.glb")
    data = glb.read_bytes()
    magic, version, length = struct.unpack("<4sII", data[:12])
    json_length, chunk_type = struct.unpack("<I4s", data[12:20])
    document = json.loads(data[20:20 + json_length])
    checks["glb_container_valid"] = magic == b"glTF" and version == 2 and length == len(data) and chunk_type == b"JSON"
    roles = {n.get("extras", {}).get("role") for n in document.get("nodes", [])}
    checks["glb_semantic_roles"] = roles == {"hull", "archive_shell", "archive_interior"}
    checks["glb_no_external_dependencies"] = not any("uri" in b for b in document.get("buffers", [])) and not document.get("images")
    checks["glb_no_environment_or_cameras"] = not document.get("cameras") and "environment" not in roles
    checks["glb_normals_match_positions"] = all(
        "NORMAL" in p["attributes"] and
        document["accessors"][p["attributes"]["NORMAL"]]["count"] ==
        document["accessors"][p["attributes"]["POSITION"]]["count"]
        for m in document["meshes"] for p in m["primitives"])
    triangles = sum(document["accessors"][p["indices"]]["count"] // 3 for m in document["meshes"] for p in m["primitives"])
    comparison = None
    if args.baseline:
        current = comparison_signatures()
        bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
        baseline = comparison_signatures()
        comparison = {name: current[name] == baseline[name] for name in current}
        checks.update({"baseline_" + name.lower() + "_unchanged": matches
                       for name, matches in comparison.items()})
    result = {"passed": all(checks.values()), "checks": checks, "external_images": external_images,
              "external_libraries": external_libraries, "room_bounds_violations": sorted(set(escaped)),
              "invalid_hull_source_meshes": invalid_meshes, "baseline_comparison": comparison,
              "glb_bytes": len(data), "glb_triangles": triangles,
              "glb_meshes": len(document["meshes"]), "blender": bpy.app.version_string,
              "limits": "Structural/resource verification only; no browser FPS or production art approval."}
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, flush=True)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
