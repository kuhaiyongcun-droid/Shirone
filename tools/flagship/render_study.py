"""Render explicit study views and record per-view wall time; CPU is the default.

blender -b --python render_study.py -- --scene ./output/flagship-blockout.blend --views hero
python render_study.py --scene ./output/flagship-blockout.blend --views hero

This script changes the loaded scene in memory, never overwrites the source blend,
and never automatically selects a remote or local GPU. OptiX requires an explicit
flag; the human workflow must first verify the connected target machine.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import bpy


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--views", default="hero", help="Comma-separated camera names, or all")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=450)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--device", choices=("cpu", "optix"), default="cpu")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def select_device(scene, choice):
    if choice == "cpu":
        scene.cycles.device = "CPU"
        return [{"type": "CPU", "name": platform.processor() or platform.machine()}]
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.refresh_devices()
    available = [d for d in prefs.devices if d.type == "OPTIX"]
    if len(available) != 1:
        raise RuntimeError("OptiX requires exactly one verified GPU for this sample; inspect preflight before choosing a different device.")
    for dev in prefs.devices:
        dev.use = dev == available[0]
    scene.cycles.device = "GPU"
    return [{"type": d.type, "name": d.name} for d in available]


def set_view(scene, view):
    coupon = view == "coupon"
    cutaway = view.startswith("archive")
    for name in ("SHIP_HULL", "ARCHIVE_INTERIOR"):
        bpy.data.collections[name].hide_render = coupon
        bpy.data.collections[name].hide_viewport = coupon
    bpy.data.collections["ARCHIVE_SHELL"].hide_render = coupon or cutaway
    bpy.data.collections["ARCHIVE_SHELL"].hide_viewport = coupon or cutaway
    bpy.data.collections["SPACE"].hide_render = view != "hero"
    bpy.data.collections["SPACE"].hide_viewport = view != "hero"
    bpy.data.collections["LIGHTING"].hide_render = coupon
    for name in ("COUPON", "COUPON_LIGHTS"):
        bpy.data.collections[name].hide_render = not coupon
        bpy.data.collections[name].hide_viewport = not coupon
    # Same camera data before/after selection; opening the cutaway only toggles a shell collection.
    scene.camera = bpy.data.objects[view]
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.08, 0.11, 0.16, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.23
    return coupon, cutaway


def peak_process_rss_mib():
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(value / (1024 * 1024 if platform.system() == "Darwin" else 1024), 2)
    except ImportError:
        return None


def main():
    args = parse()
    if not (64 <= args.width <= 8192 and 64 <= args.height <= 8192 and 1 <= args.samples <= 4096):
        raise SystemExit("Invalid render size or sample count")
    if args.threads < 1:
        raise SystemExit("Thread count must be positive")
    path = args.scene.resolve()
    output = (args.output or path.parent / "renders").resolve()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = next(s for s in bpy.data.scenes if s.name.startswith("KUHAI"))
    bpy.context.window.scene = scene
    available = [o.name for o in bpy.data.collections["CAMERAS"].objects]
    views = available if args.views == "all" else args.views.split(",")
    if any(v not in available for v in views):
        raise SystemExit("Unknown view; choose from " + ", ".join(available))
    result_path = output / ("benchmark-" + "-".join(views) + ".json")
    if not args.overwrite and (result_path.exists() or any((output / (v + ".png")).exists() for v in views)):
        raise SystemExit("Render exists. Use a different output directory or --overwrite.")
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.max_bounces = 4
    scene.render.threads_mode = "FIXED"
    scene.render.threads = args.threads
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    devices = select_device(scene, args.device)
    record = {
        "blender": bpy.app.version_string, "system": platform.system(),
        "device_mode": args.device, "devices": devices,
        "width": args.width, "height": args.height, "samples": args.samples,
        "threads": args.threads, "denoise": True, "adaptive_sampling": False,
        "max_bounces": 4, "source_blend": path.name, "renders": [],
        "note": "Offline render measurements, not browser FPS or GPU memory measurements."
    }
    for view in views:
        set_view(scene, view)
        scene.render.filepath = str(output / (view + ".png"))
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        seconds = round(time.perf_counter() - start, 3)
        record["renders"].append({"view": view, "seconds": seconds, "file": view + ".png",
                                  "peak_process_rss_mib": peak_process_rss_mib()})
        # Persist after every frame to make interrupted batches recoverable.
        result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("STUDY_RENDER " + json.dumps(record["renders"][-1]), flush=True)


if __name__ == "__main__":
    main()
