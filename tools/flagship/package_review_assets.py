"""Create the private review's portable asset bundle using only Python stdlib."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--assets", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
names = ("flagship.glb", "archive.glb", "overview.webp", "archive.webp", "model-manifest.json")
hashes = {name: hashlib.sha256((args.assets / name).read_bytes()).hexdigest() for name in names}
args.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(args.assets / name, "assets/" + name)
    archive.writestr("SHA256.json", json.dumps(hashes, indent=2) + "\n")
print(json.dumps({"bytes": args.output.stat().st_size, "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
