"""Open the relocated coating sample, check resources, and render on CPU."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy


def main():
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--render", action="store_true")
    args = p.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(args.scene.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    source, baked = (bpy.data.collections.get(n) for n in ("SOURCE_COATING", "BAKED_COATING"))
    images = []
    for image in bpy.data.images:
        if image.type == "IMAGE" and image.users:
            local = Path(bpy.path.abspath(image.filepath)).resolve()
            images.append({"name": image.name, "path": image.filepath,
                           "packed": bool(image.packed_file), "size": list(image.size),
                           "local_relative_file": image.filepath.startswith("//") and local.is_file()
                           and local.is_relative_to(args.scene.parent.resolve())})
    checks = {
        "one_scene": len(bpy.data.scenes) == 1,
        "editable_source_hidden": bool(source and source.hide_render and source.hide_viewport
                                        and len(source.objects) == 1),
        "baked_cover_visible": bool(baked and not baked.hide_render and len(baked.objects) == 1),
        "resources_packed_and_relative": bool(images) and all(i["packed"] and i["local_relative_file"] for i in images),
        "resources_decode": all(min(i["size"]) > 0 for i in images),
    }
    record = {"sample_sha256": digest, "blender": bpy.app.version_string,
              "images": images, "checks": checks, "rendered": False}
    if all(checks.values()) and args.render:
        scene.render.engine = "CYCLES"
        scene.cycles.device, scene.cycles.samples = "CPU", 24
        scene.render.threads_mode, scene.render.threads = "FIXED", 6
        scene.render.resolution_x = scene.render.resolution_y = 512
        scene.render.resolution_percentage = 100
        scene.render.filepath = str((args.output/"relocated-cover.png").resolve())
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record.update(rendered=True, device="CPU", seconds=round(time.perf_counter()-start, 3))
    checks["input_unchanged"] = hashlib.sha256(args.scene.read_bytes()).hexdigest() == digest
    record["passed"] = all(checks.values())
    (args.output/"sample-relocation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
