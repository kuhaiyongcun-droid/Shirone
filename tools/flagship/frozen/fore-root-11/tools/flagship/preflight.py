"""Read-only Blender/CPU/GPU inventory. Does not start any render or install software.

blender -b --python preflight.py -- --output ./preflight.json
python preflight.py --output ./preflight.json
"""

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def inventory():
    result = {
        "machine_hostname": socket.gethostname(),
        "system": platform.platform(), "architecture": platform.machine(),
        "python": platform.python_version(), "logical_cpu_count": os.cpu_count(),
        "cgroup_cpu_max": read_optional("/sys/fs/cgroup/cpu.max"),
        "cgroup_memory_max_bytes": read_optional("/sys/fs/cgroup/memory.max"),
        "blender_executable_on_path": shutil.which("blender"),
        "nvidia_smi_on_path": shutil.which("nvidia-smi"),
        "authorization_note": "Inventory is not authorization. Verify user-connected target before local workload.",
        "render_started": False,
    }
    if result["nvidia_smi_on_path"]:
        try:
            query = subprocess.run([result["nvidia_smi_on_path"], "--query-gpu=name,driver_version,memory.total,memory.free",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15)
            result["nvidia_smi"] = {"returncode": query.returncode, "gpus_csv": query.stdout.strip(), "error": query.stderr.strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["nvidia_smi_error"] = str(exc)
    try:
        import bpy
        result["blender"] = bpy.app.version_string
        result["blender_build_hash"] = bpy.app.build_hash.decode()
        result["cycles_compiled"] = bpy.app.build_options.cycles
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        result["cycles_devices"] = [{"name": d.name, "type": d.type} for d in prefs.devices]
    except (ImportError, KeyError, RuntimeError) as exc:
        result["blender_error"] = str(exc)
    result["python_packages"] = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
                                  if d.metadata["Name"].lower() in {"bpy", "numpy", "cython", "zstandard", "requests"}}
    return result


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = inventory()
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
