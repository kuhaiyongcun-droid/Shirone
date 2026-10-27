"""Read-only static release preflight; not a substitute for nginx -t or a browser."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Final assembled dist directory")
    args = parser.parse_args()
    root = args.dist.resolve(strict=True)
    if not root.is_dir():
        raise SystemExit("dist must be a directory")
    errors = []
    forbidden_suffix = re.compile(r"\.(?:map|ts|tsx|jsx|astro|vue|svelte|md|mdx|py|pyc|sh|ps1|bat|cmd|blend[0-9]*|pem|key|env|ini|toml|ya?ml|lock|bak|log|sql)(?:\.(?:gz|br))?$", re.I)
    forbidden_names = re.compile(r"(?:site\.json|package(?:-lock)?\.json|tsconfig(?:\.[^/]+)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Dockerfile|Makefile)(?:\.(?:gz|br))?$", re.I)
    forbidden_dirs = {"src", "node_modules", "deployment", "evidence", "scripts", "content", "runtime"}
    files = []

    def redirected(item):
        return item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction())

    def check_path(item):
        relative = item.relative_to(root)
        name = relative.as_posix()
        parts = relative.parts
        if any(part.startswith(".") and not (i == 0 and part == ".well-known") for i, part in enumerate(parts)):
            errors.append({"path": name, "reason": "hidden_path"})
        top = parts[1] if parts[0] == "blog" and len(parts) > 1 else parts[0]
        if top.lower() in forbidden_dirs:
            errors.append({"path": name, "reason": "source_or_delivery_directory"})
        return name

    for directory, subdirs, filenames in os.walk(root, followlinks=False):
        for dirname in sorted(subdirs[:]):
            item = Path(directory) / dirname
            name = check_path(item)
            if redirected(item):
                errors.append({"path": name, "reason": "symlink_or_junction_not_publishable"})
                subdirs.remove(dirname)
        for filename in sorted(filenames):
            item = Path(directory) / filename
            name = check_path(item)
            if redirected(item):
                errors.append({"path": name, "reason": "symlink_or_junction_not_publishable"})
                continue
            if not item.is_file():
                errors.append({"path": name, "reason": "non_regular_file"})
                continue
            if forbidden_suffix.search(name) or forbidden_names.fullmatch(item.name):
                errors.append({"path": name, "reason": "source_config_or_private_artifact"})
            digest = hashlib.sha256()
            with item.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            files.append({"path": name, "bytes": item.stat().st_size, "sha256": digest.hexdigest()})
    for required in ("index.html", "blog/index.html", "404.html"):
        if not (root / required).is_file():
            errors.append({"path": required, "reason": "required_entry_missing"})
    output = {
        "scope": "read_only_dist_inventory_and_publication_boundary",
        "dist": str(root),
        "passed": not errors,
        "files_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "errors": errors,
        "files": sorted(files, key=lambda item: item["path"]),
        "not_executed": ["nginx_-t", "server_HTTP", "TLS", "browser", "filing_approval"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
