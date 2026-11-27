"""Package the authoring source and existing dependencies, or restore to a NEW directory.

No installation, network, subprocess, user configuration or credential access.
Dependency directory links are recorded as internal targets, never archived as links.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "DEVELOPMENT-MANIFEST.json"
TOKEN = "__KUHAI_DEVELOPMENT_ROOT__"
DENIED = {".git", ".env", ".npmrc", ".pypirc", ".netrc", "credentials", "id_rsa", "id_ed25519", "runtime.local.json", "toolchain-local.json"}
MACHINE_METADATA = {".modules.yaml", ".pnpm-workspace-state-v1.json"}
RESTORE_DIRECTORIES = ("evidence", "delivery-packages", "blog/public/assets")


def relative(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\\:*?"<>|') or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"Unsafe relative path: {value!r}")
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(x in (".", "..", "") or x.endswith((".", " ")) for x in p.parts):
        raise ValueError(f"Non-canonical path: {value!r}")
    for part in p.parts:
        if re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part, re.I):
            raise ValueError(f"Reserved path: {value}")
    return p


def redirected(path):
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & 0x400) or path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def plain_ancestry(path, root):
    for parent in (path, *path.parents):
        if redirected(parent):
            raise ValueError(f"Package path traverses a directory link: {parent}")
        if parent == root:
            return
    raise ValueError("Package path is not under its declared root")


def sha_file(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
            size += len(b)
    return {"bytes": size, "sha256": h.hexdigest()}


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def new_file(path, data):
    with path.open("xb") as f:
        f.write(data)


def denied(name):
    name = name.casefold()
    return name in DENIED or name.startswith(".env.") or name.endswith((".pem", ".key", ".p12", ".pfx"))


def source_files(root, policy):
    """Explicit authoring trees; never enumerate unrelated history or credential directories."""
    exclusions = policy.get("exclude", [])
    result = {}

    def excluded(rel):
        parts = PurePosixPath(rel).parts
        return any(denied(x) for x in parts) or any(rel == x or rel.startswith(x.rstrip("/") + "/") for x in exclusions) or "__pycache__" in parts or rel.endswith(".pyc")

    def add(path):
        rel = path.relative_to(root).as_posix()
        relative(rel)
        if excluded(rel):
            return
        if redirected(path) or not path.is_file():
            raise ValueError(f"Source must be a regular file: {rel}")
        result[rel] = path

    for value in policy["files"]:
        rel = relative(value)
        p = root.joinpath(*rel.parts)
        plain_ancestry(p, root)
        add(p)
    for value in policy["trees"]:
        rel = relative(value)
        p = root.joinpath(*rel.parts)
        plain_ancestry(p, root)
        if redirected(p) or not p.is_dir():
            raise ValueError(f"Missing or linked source tree: {value}")
        for base, ds, fs in os.walk(p, followlinks=False):
            for name in list(ds):
                child = Path(base) / name
                child_rel = child.relative_to(root).as_posix()
                if excluded(child_rel):
                    ds.remove(name)
                elif redirected(child):
                    raise ValueError(f"Linked source directory: {child_rel}")
            for name in fs:
                add(Path(base) / name)
    return result, []


def dependency_files(root):
    result, links = {}, []
    for package in ("blog", "ship"):
        base = root / package / "node_modules"
        plain_ancestry(base, root)
        if not base.is_dir() or redirected(base):
            raise ValueError(f"Missing independent dependency directory: {base}")
        for directory, ds, fs in os.walk(base, followlinks=False):
            for name in list(ds):
                p = Path(directory) / name
                if denied(name) or name in (".cache", ".vite", ".astro"):
                    ds.remove(name)
                elif redirected(p):
                    ds.remove(name)
                    target = p.resolve(strict=True)
                    if not target.is_relative_to(base) or not target.is_dir() or redirected(target):
                        raise ValueError(f"Dependency link escapes its package: {p}")
                    links.append({"path": p.relative_to(root).as_posix(), "target": target.relative_to(root).as_posix()})
            for name in fs:
                if denied(name) or name in MACHINE_METADATA:
                    continue
                p = Path(directory) / name
                if redirected(p):
                    raise ValueError(f"Unexpected dependency file symlink (not copied): {p}")
                if not p.is_file():
                    raise ValueError(f"Non-regular dependency file: {p}")
                result[p.relative_to(root).as_posix()] = p
    return result, sorted(links, key=lambda x: x["path"])


def shim_data(path, root):
    """PNPM generated shims contain NODE_PATH strings. Relocate only this known file class."""
    if ".bin" not in path.relative_to(root).parts:
        return None
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    forward_root = str(root).replace("\\", "/")
    changed = text.replace(forward_root, TOKEN).replace(str(root).replace("/", "\\"), TOKEN)
    if re.match(r"^[A-Za-z]:/", forward_root):
        wsl_root = "/mnt/" + forward_root[0].lower() + forward_root[2:]
        changed = changed.replace(wsl_root, TOKEN)
    if changed == text:
        return None
    return changed.encode("utf-8"), sha_file(path)


def archive_write(root, output, kind, files, links, source_identity=None):
    if output.exists() or redirected(output):
        raise ValueError("Refusing to overwrite an existing archive")
    partial = output.with_suffix(output.suffix + ".partial")
    if len({x.casefold() for x in files}) != len(files):
        raise ValueError("Case-insensitive filename collision")
    timestamp = datetime.now(timezone.utc)
    manifest = {"schema": "kuhai-development-archive-v1", "kind": kind, "created_utc": timestamp.isoformat(),
                "platform": {"system": platform.system(), "machine": platform.machine()} if kind == "dependencies" else None,
                "source_archive": source_identity, "files": [], "directory_links": links,
                "relocation_token": TOKEN, "network_or_installation_executed": False,
                "omitted_dependency_metadata": sorted(MACHINE_METADATA) if kind == "dependencies" else []}
    started = time.monotonic()
    with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for number, name in enumerate(sorted(files), 1):
            relative(name)
            path = files[name]
            transformed = shim_data(path, root) if kind == "dependencies" else None
            info = zipfile.ZipInfo(name, timestamp.timetuple()[:6])
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if ".bin" in path.parts or os.access(path, os.X_OK) else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            digest, crc, count = hashlib.sha256(), 0, 0
            with archive.open(info, "w", force_zip64=True) as writer:
                if transformed:
                    chunks = (transformed[0],)
                    source = None
                else:
                    source = path.open("rb")
                    chunks = iter(lambda: source.read(1024 * 1024), b"")
                try:
                    for chunk in chunks:
                        writer.write(chunk)
                        digest.update(chunk)
                        crc = zlib.crc32(chunk, crc)
                        count += len(chunk)
                finally:
                    if source:
                        source.close()
            row = {"path": name, "bytes": count, "sha256": digest.hexdigest(), "crc32": f"{crc & 0xffffffff:08x}"}
            if transformed:
                row["relocation"] = "pnpm-shim-root-token"
                row["original"] = transformed[1]
            manifest["files"].append(row)
            if number % 5000 == 0:
                print(json.dumps({"phase": "archive", "kind": kind, "files": number, "total": len(files), "seconds": round(time.monotonic() - started)}), flush=True)
        manifest["files_count"] = len(files)
        manifest["total_bytes"] = sum(x["bytes"] for x in manifest["files"])
        archive.writestr(MANIFEST, json_bytes(manifest))
    verified = verify_archive(partial)
    os.link(partial, output)
    partial.unlink()
    new_file(output.with_suffix(".manifest.json"), json_bytes(manifest))
    return {"name": output.name, **sha_file(output), "verified": verified}


def read_manifest(archive):
    try:
        info = archive.getinfo(MANIFEST)
    except KeyError as error:
        raise ValueError("Missing development manifest") from error
    if info.file_size > 64 * 1024 * 1024:
        raise ValueError("Oversize manifest")
    data = json.loads(archive.read(info))
    if data.get("schema") != "kuhai-development-archive-v1" or data.get("kind") not in ("source", "dependencies"):
        raise ValueError("Unsupported development package")
    return data


def validate_layout(manifest):
    rows = manifest.get("files", [])
    links = manifest.get("directory_links", [])
    names = []
    directories = set()
    for row in rows:
        p = relative(row["path"])
        if p.name == MANIFEST or not isinstance(row["bytes"], int) or row["bytes"] < 0 or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]):
            raise ValueError("Invalid payload record")
        if row.get("relocation") and (manifest["kind"] != "dependencies" or row["relocation"] != "pnpm-shim-root-token" or ".bin" not in p.parts):
            raise ValueError("Unsupported relocation record")
        names.append(p.as_posix())
        directories.update(parent.as_posix() for parent in p.parents if parent.as_posix() != ".")
    all_names = names + [relative(x["path"]).as_posix() for x in links]
    if len({x.casefold() for x in all_names}) != len(all_names):
        raise ValueError("Duplicate/case-colliding payload or link")
    directory_keys = {v.casefold() for v in directories}
    if any(x.casefold() in directory_keys for x in all_names):
        raise ValueError("File/link collides with a real directory")
    leaf_keys = {x.casefold() for x in all_names}
    if any(parent.as_posix().casefold() in leaf_keys for name in all_names for parent in PurePosixPath(name).parents if parent.as_posix() != "."):
        raise ValueError("File/link is nested under another file/link")
    for link in links:
        target, path = relative(link["target"]), relative(link["path"])
        if manifest["kind"] != "dependencies" or len(path.parts) < 3 or path.parts[:2] not in (("blog", "node_modules"), ("ship", "node_modules")) or target.parts[:2] != path.parts[:2]:
            raise ValueError("Dependency link crosses its owning dependency tree")
        if target.as_posix() not in directories:
            raise ValueError("Dependency link target is not an existing real directory")
        if path == target or target in path.parents:
            raise ValueError("Dependency link forms an ancestor cycle")
    if manifest.get("files_count") != len(rows) or manifest.get("total_bytes") != sum(x["bytes"] for x in rows):
        raise ValueError("Manifest totals differ")
    return {x["path"]: x for x in rows}


def verify_archive(path, expected_sha=None):
    if expected_sha and sha_file(path)["sha256"] != expected_sha:
        raise ValueError("Archive SHA256 differs from the requested package")
    with zipfile.ZipFile(path) as archive:
        manifest = read_manifest(archive)
        rows = validate_layout(manifest)
        infos = archive.infolist()
        if len(infos) != len(rows) + 1 or {x.filename for x in infos} != set(rows) | {MANIFEST}:
            raise ValueError("ZIP adds, duplicates or omits payload entries")
        for info in infos:
            relative(info.filename)
            if info.is_dir() or info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("ZIP directories, encrypted entries and symbolic links are not allowed")
            if info.filename == MANIFEST:
                continue
            row = rows[info.filename]
            if info.file_size != row["bytes"] or info.CRC != int(row["crc32"], 16):
                raise ValueError(f"ZIP size/CRC mismatch: {info.filename}")
            digest = hashlib.sha256()
            with archive.open(info) as reader:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != row["sha256"]:
                raise ValueError(f"ZIP SHA256 mismatch: {info.filename}")
    return {"kind": manifest["kind"], "files": len(rows), "bytes": manifest["total_bytes"], "links": len(manifest["directory_links"]), "all_files_sha256_crc32_pass": True}


def check_windows_restore_paths(target, manifests):
    """Reject legacy Win32 limits before creating any part of the restore root."""
    if platform.system() != "Windows":
        return
    files = {target / "DEVELOPMENT-RESTORE.json"}
    directories = {target, *(target / name for name in RESTORE_DIRECTORIES)}
    for manifest in manifests:
        for row in manifest["files"]:
            files.add(target.joinpath(*relative(row["path"]).parts))
        for link in manifest["directory_links"]:
            directories.add(target.joinpath(*relative(link["path"]).parts))
            directories.add(target.joinpath(*relative(link["target"]).parts))
    for path in (*files, *directories):
        for parent in path.parents:
            if not parent.is_relative_to(target):
                break
            directories.add(parent)
    for kind, paths, limit in (("file", files, 260), ("directory/link", directories, 248)):
        for path in sorted(paths):
            units = len(str(path).encode("utf-16-le", errors="surrogatepass")) // 2
            if units >= limit:
                raise ValueError(f"Windows restore {kind} path is {units} UTF-16 code units (must be <{limit}): {path}. Use a shorter NEW --target root; no target directory was created and no system setting was changed.")


def restore(source, dependencies, target, expected_source_sha=None, expected_dependencies_sha=None):
    if sys.version_info < (3, 12):
        raise ValueError("Python 3.12 or later is required for verified directory-link handling")
    # Refuse an existing directory, including an empty one, before any writes.
    target = Path(os.path.abspath(target))
    if any(c in str(target) for c in "$`%&|<>^!;()'\"\r\n"):
        raise ValueError("Restore target contains unsupported shell metacharacters; use letters, numbers, spaces, Chinese, hyphens or underscores")
    if target.exists() or redirected(target) or not target.parent.is_dir() or target == target.parent:
        raise ValueError("Restore target must be a new directory with an existing parent")
    for parent in target.parents:
        if redirected(parent):
            raise ValueError("Restore parent traverses a directory link")
    target = target.parent.resolve() / target.name
    if any(c in str(target) for c in "$`%&|<>^!;()'\"\r\n"):
        raise ValueError("Resolved restore target contains unsupported shell metacharacters")
    paths = [source] + ([dependencies] if dependencies else [])
    results = [verify_archive(source, expected_source_sha)]
    if dependencies:
        results.append(verify_archive(dependencies, expected_dependencies_sha))
    manifests = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            manifests.append(read_manifest(archive))
    if manifests[0]["kind"] != "source":
        raise ValueError("--source requires a source package")
    if dependencies:
        dependency_manifest = manifests[1]
        if dependency_manifest["kind"] != "dependencies" or dependency_manifest["platform"] != {"system": platform.system(), "machine": platform.machine()}:
            raise ValueError("Offline native dependencies do not match this OS/architecture")
        if dependency_manifest["source_archive"] != sha_file(source):
            raise ValueError("Dependency package belongs to a different source ZIP")
    names = [row["path"].casefold() for m in manifests for row in m["files"]]
    if len(set(names)) != len(names):
        raise ValueError("Source and dependency archives overlap")
    validate_layout({"kind": "dependencies", "files": [row for m in manifests for row in m["files"]],
                     "directory_links": [link for m in manifests for link in m["directory_links"]],
                     "files_count": len(names), "total_bytes": sum(m["total_bytes"] for m in manifests)})
    check_windows_restore_paths(target, manifests)
    required = sum(m["total_bytes"] for m in manifests) * 1.15 + 128 * 1024 * 1024
    if shutil.disk_usage(target.parent).free < required:
        raise ValueError("Insufficient free space for checked restore")
    target.mkdir()
    receipt = {"schema": "kuhai-development-restore-v1", "created_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
               "source": {"name": source.name, **sha_file(source)}, "dependencies": {"name": dependencies.name, **sha_file(dependencies)} if dependencies else None,
               "archive_verification": results, "relocated_files": [], "directory_links_recreated": 0,
               "network_installation_or_build_executed": False}
    try:
        for path, manifest in zip(paths, manifests):
            with zipfile.ZipFile(path) as archive:
                for row in manifest["files"]:
                    dest = target.joinpath(*relative(row["path"]).parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if row.get("relocation"):
                        if row["relocation"] != "pnpm-shim-root-token" or ".bin" not in relative(row["path"]).parts:
                            raise ValueError("Unsupported relocation")
                        raw = archive.read(row["path"])
                        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                            raise ValueError("Relocated shim changed after archive verification")
                        text = raw.decode("utf-8")
                        # Forward slashes are valid for node/NODE_PATH on Windows and shell shims.
                        data = text.replace(TOKEN, target.as_posix()).encode("utf-8")
                        new_file(dest, data)
                        receipt["relocated_files"].append({"path": row["path"], "archived_sha256": row["sha256"], **sha_file(dest)})
                    else:
                        with archive.open(row["path"]) as reader, dest.open("xb") as writer:
                            shutil.copyfileobj(reader, writer, 1024 * 1024)
                        if sha_file(dest) != {"bytes": row["bytes"], "sha256": row["sha256"]}:
                            raise ValueError(f"Restored file mismatch: {row['path']}")
                    if os.name != "nt":
                        mode = archive.getinfo(row["path"]).external_attr >> 16
                        dest.chmod(stat.S_IMODE(mode) & 0o777 or 0o644)
            for link in manifest["directory_links"]:
                dest = target.joinpath(*relative(link["path"]).parts)
                actual = target.joinpath(*relative(link["target"]).parts)
                if not actual.is_dir() or redirected(actual) or not actual.resolve().is_relative_to(target):
                    raise ValueError("Restored dependency target escapes new directory")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or redirected(dest):
                    raise ValueError("Dependency link output already exists")
                if os.name == "nt":
                    import _winapi
                    _winapi.CreateJunction(str(actual), str(dest))
                else:
                    dest.symlink_to(os.path.relpath(actual, dest.parent), target_is_directory=True)
                if dest.resolve() != actual.resolve():
                    raise ValueError("Created dependency link resolves incorrectly")
                receipt["directory_links_recreated"] += 1
        for name in RESTORE_DIRECTORIES:
            (target / name).mkdir(parents=True, exist_ok=True)
        receipt["passed"] = True
    finally:
        new_file(target / "DEVELOPMENT-RESTORE.json", json_bytes(receipt))
    return {"target": str(target), "passed": True, "files": len(names), "links": receipt["directory_links_recreated"], "relocated_shims": len(receipt["relocated_files"])}


def pack(args):
    if sys.version_info < (3, 12):
        raise ValueError("Python 3.12 or later is required for verified directory-link handling")
    if not re.fullmatch(r"kuhai-dev-[a-zA-Z0-9_-]{1,64}", args.name):
        raise ValueError("Use a versioned kuhai-dev-NAME")
    policy_path = ROOT / "scripts/developer-package-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    files, _ = source_files(ROOT, policy)
    deps, links = dependency_files(ROOT)
    output = ROOT / "developer-packages" / args.name
    plain_ancestry(output, ROOT)
    if output.exists() or redirected(output):
        raise ValueError("Refusing to overwrite developer package")
    output.parent.mkdir(exist_ok=True)
    output.mkdir()
    source = output / (args.name + "-source.zip")
    source_result = archive_write(ROOT, source, "source", files, [])
    print(json.dumps({"source": source_result}, ensure_ascii=False), flush=True)
    dep = output / (args.name + "-dependencies-" + platform.system().lower() + "-" + platform.machine().lower() + ".zip")
    dep_result = archive_write(ROOT, dep, "dependencies", deps, links, sha_file(source))
    new_file(output / "恢复开发包.py", Path(__file__).read_bytes())
    new_file(output / "README-开发包.txt", (ROOT / "开发与发布说明-v2.txt").read_bytes())
    outputs = [source_result, dep_result]
    new_file(output / "PACKAGE-RESULT.json", json_bytes({"schema": "kuhai-development-package-result-v1", "passed": True, "outputs": outputs,
                                                        "policy_sha256": sha_file(policy_path)["sha256"], "platform_note": "Offline dependencies are platform-specific; Node and Python are installed separately. No dependency installation or build is performed by this packager."}))
    checksums = "".join(f"{sha_file(p)['sha256']}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file())
    new_file(output / "SHA256SUMS.txt", checksums.encode("utf-8"))
    return {"passed": True, "directory": str(output), "outputs": outputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--name", required=True)
    v = sub.add_parser("verify")
    v.add_argument("archive", type=Path)
    v.add_argument("--sha256")
    r = sub.add_parser("restore")
    r.add_argument("--source", type=Path, required=True)
    r.add_argument("--dependencies", type=Path)
    r.add_argument("--target", type=Path, required=True)
    r.add_argument("--source-sha256")
    r.add_argument("--dependencies-sha256")
    args = parser.parse_args()
    if args.command == "pack":
        result = pack(args)
    elif args.command == "verify":
        result = verify_archive(args.archive, args.sha256)
    else:
        result = restore(args.source, args.dependencies, args.target, args.source_sha256, args.dependencies_sha256)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Development package stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
