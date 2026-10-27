"""Create a new offline deployment ZIP from verified static files; never deploys."""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

RELEASE = Path(__file__).resolve().parents[1]
DEPLOYMENT_FILES = (
    "nginx/acme.conf", "nginx/cache-maps.conf", "nginx/http-bootstrap.conf",
    "nginx/https-production.conf", "nginx/mime.types", "nginx/site.conf",
    "preflight.py", "switch-release.sh", "部署与更新说明.txt",
)
PRIVATE_SUFFIX = re.compile(r"\.(?:map|ts|tsx|jsx|astro|vue|svelte|md|mdx|py|pyc|sh|ps1|bat|cmd|blend[0-9]*|pem|key|env|ini|toml|ya?ml|lock|bak|log|sql)(?:\.(?:gz|br))?$", re.I)
PRIVATE_NAMES = re.compile(r"(?:site\.json|package(?:-lock)?\.json|tsconfig(?:\.[^/]+)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Dockerfile|Makefile)(?:\.(?:gz|br))?$", re.I)
PRIVATE_DIRS = {"src", "node_modules", "deployment", "evidence", "scripts", "content", "runtime"}
PRIVATE_AUTHORING_ROOTS = {"authoring-private", "preview-work"}
PREVIEW_SENTINELS = ("PREVIEW-ONLY.json", "draft-preview-receipt.json")
HEX_SHA = re.compile(r"[0-9a-f]{64}")


def redirected(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def reject_preview_input(path):
    """Reject private origins and marked previews, including renamed copies."""
    path = Path(path)
    if not path.is_absolute():
        path = RELEASE / path
    if not path.is_relative_to(RELEASE) or ".." in path.relative_to(RELEASE).parts:
        raise ValueError("Publication input must remain inside this release")
    relative = path.relative_to(RELEASE)
    if relative.parts and relative.parts[0].casefold() in PRIVATE_AUTHORING_ROOTS:
        raise ValueError("Private authoring/preview input cannot be published: " + relative.as_posix())
    current = RELEASE
    for part in relative.parts:
        current /= part
        if redirected(current):
            raise ValueError("Linked publication input is forbidden: " + relative.as_posix())
    current = path if path.is_dir() else path.parent
    while True:
        for filename in PREVIEW_SENTINELS:
            marker = current / filename
            # Presence is enough: malformed or linked preview receipts must
            # never become ordinary publishable JSON assets.
            if marker.exists() or redirected(marker):
                raise ValueError("Preview-only marker/receipt prohibits publication: " + marker.relative_to(RELEASE).as_posix())
        if current == RELEASE:
            break
        current = current.parent


def safe_relative(value):
    if not isinstance(value, str) or not value or any(char in value for char in '\\:<>"|?*') or any(ord(char) < 32 for char in value):
        raise ValueError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError(f"Non-canonical relative path: {value}")
    if any(part.endswith((".", " ")) or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I) for part in path.parts):
        raise ValueError(f"Non-portable filename: {value}")
    return path


def local_path(value, directory=False, required=True):
    supplied = Path(value)
    path = supplied if supplied.is_absolute() else RELEASE / supplied
    if not path.is_relative_to(RELEASE):
        raise ValueError("Every input and output must stay under this release")
    relative = path.relative_to(RELEASE)
    if ".." in relative.parts:
        raise ValueError("Parent traversal is not allowed")
    candidate = RELEASE
    for part in relative.parts:
        candidate = candidate / part
        if redirected(candidate):
            raise ValueError(f"Symlink/junction is not allowed: {candidate}")
    if path.resolve(strict=required) != path:
        raise ValueError(f"Path resolves outside its declared location: {path}")
    if required and (not path.is_dir() if directory else not path.is_file()):
        raise ValueError(f"Required {'directory' if directory else 'file'} is missing: {path}")
    reject_preview_input(path)
    return path


def file_fingerprint(path):
    path = local_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Only regular files can be packaged: {path}")
    digest = hashlib.sha256()
    crc = 0
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or size != before.st_size:
        raise ValueError(f"Source changed while hashing: {path}")
    return {"bytes": size, "sha256": digest.hexdigest(), "crc32": f"{crc & 0xffffffff:08x}"}


def bytes_fingerprint(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "crc32": f"{zlib.crc32(data) & 0xffffffff:08x}"}


def read_json(path):
    path = local_path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError(f"JSON input exceeds inspection limit: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inventory_rows(rows):
    inventory = {}
    folded = set()
    if not isinstance(rows, list) or not rows:
        raise ValueError("A non-empty verified file inventory is required")
    for row in rows:
        name = safe_relative(row.get("path")).as_posix()
        if name.casefold() in folded or type(row.get("bytes")) is not int or row["bytes"] < 0 or not HEX_SHA.fullmatch(row.get("sha256", "")):
            raise ValueError(f"Invalid or duplicate inventory row: {name}")
        folded.add(name.casefold())
        inventory[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    return inventory


def enforce_webroot(relative):
    parts = safe_relative(relative).parts
    if any(part.startswith(".") and not (index == 0 and part == ".well-known") for index, part in enumerate(parts)):
        raise ValueError(f"Hidden file in webroot: {relative}")
    effective = parts[1:] if parts[0] == "blog" else parts
    if any(part.lower() in PRIVATE_DIRS for part in effective):
        raise ValueError(f"Source/delivery directory in webroot: {relative}")
    if PRIVATE_SUFFIX.search(parts[-1]) or PRIVATE_NAMES.fullmatch(parts[-1]):
        raise ValueError(f"Source, source-map or private config in webroot: {relative}")


def actual_files(root):
    paths = {}
    for directory, subdirs, filenames in os.walk(root, followlinks=False):
        reject_preview_input(Path(directory))
        subdirs.sort()
        for name in subdirs:
            path = Path(directory) / name
            if redirected(path):
                raise ValueError(f"Linked directory in webroot: {path}")
            enforce_webroot(path.relative_to(root).as_posix())
        for name in sorted(filenames):
            path = local_path(Path(directory) / name)
            relative = path.relative_to(root).as_posix()
            enforce_webroot(relative)
            paths[relative] = path
    return paths


def source_entry(path, archive_path, expected=None):
    archive_path = safe_relative(archive_path).as_posix()
    fingerprint = file_fingerprint(path)
    if expected and any(fingerprint[key] != expected[key] for key in ("bytes", "sha256")):
        raise ValueError(f"Source differs from verified evidence: {path}")
    return {"path": archive_path, **fingerprint, "provenance": {"kind": "unchanged_file", "source": str(path.relative_to(RELEASE))}, "_source": path}


def generated_entry(data, archive_path, provenance):
    return {"path": safe_relative(archive_path).as_posix(), **bytes_fingerprint(data), "provenance": provenance, "_data": data}


def public_row(entry):
    return {key: value for key, value in entry.items() if not key.startswith("_")}


def portable_deployment_guide(text):
    # Remove workspace-only historical status, not deployment instructions.
    text = text.split("\n截至 v2 的已读交付证据", 1)[0]
    lines = [line for line in text.splitlines() if not line.startswith("部署配置修订：")]
    text = "\n".join(lines) + "\n\n包内完整性以根 MANIFEST.json、PAYLOAD-SHA256SUMS.txt 为准。历史工作区清单、状态和证据没有放入此部署包；本轮完成与未完成项以根交付报告为准。\n"
    if "DELIVERY-SHA256" in text or "history/v1" in text:
        raise ValueError("Deployment guide changed; inspect its portability transformation before packaging")
    return text.encode("utf-8")


def third_party_entries():
    """Collect inspected local license texts; this is not a license clearance."""
    fixed = (
        ("Shirone", "blog/LICENSE", "licenses/Shirone-LICENSE.txt"),
        ("Three.js", "ship/public/assets/THREE-LICENSE.txt", "licenses/Three-LICENSE.txt"),
        ("Draco", "blog/tools/flagship/review/public/assets/DRACO-LICENSE.txt", "licenses/Draco-LICENSE.txt"),
        ("KaTeX 0.16.47", "blog/node_modules/.pnpm/katex@0.16.47/node_modules/katex/LICENSE", "licenses/KaTeX-LICENSE.txt"),
    )
    entries = []
    notices = []
    for component, source, target in fixed:
        entry = source_entry(local_path(source), target)
        entries.append(entry)
        notices.append({"component": component, "source": source, "packaged_as": target, **{key: entry[key] for key in ("bytes", "sha256", "crc32")}})

    font_record_path = local_path("blog/docs/kuhai/release-v1/local-font-sources.json")
    font_record = read_json(font_record_path)
    if font_record.get("generatedBy") != "prepare-local-fonts.mjs" or font_record.get("network") is not False:
        raise ValueError("Unexpected local font source record")
    rows = font_record.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Local font source record has no files")
    verified = inventory_rows([{"path": row["destination"], "bytes": row["bytes"], "sha256": row["sha256"]} for row in rows])
    required_font_notices = {"LICENSE-Outfit.txt", "LICENSE-JetBrains-Mono.txt"}
    found_font_notices = set()
    for row in rows:
        relative = safe_relative(row["destination"])
        if relative.parent.as_posix() != "src/assets/fonts/kuhai-local":
            raise ValueError("Font source record points outside the inspected local font directory")
        path = local_path(RELEASE / "blog" / relative)
        fingerprint = file_fingerprint(path)
        if any(fingerprint[key] != verified[relative.as_posix()][key] for key in ("bytes", "sha256")):
            raise ValueError(f"Font source/notice changed since its source record: {relative}")
        if relative.name.startswith("LICENSE-") and relative.suffix == ".txt":
            if PurePosixPath(row["source"]).name != "LICENSE":
                raise ValueError("Font notice is not recorded as an original package LICENSE")
            target = "licenses/fonts/" + relative.name
            entry = source_entry(path, target, verified[relative.as_posix()])
            entry["provenance"]["original_package_path"] = row["source"]
            entry["provenance"]["font_source_record"] = font_record_path.relative_to(RELEASE).as_posix()
            entries.append(entry)
            found_font_notices.add(relative.name)
            notices.append({"component": relative.stem.removeprefix("LICENSE-"), "source": path.relative_to(RELEASE).as_posix(), "original_package_path": row["source"], "packaged_as": target, **fingerprint})
    if not required_font_notices.issubset(found_font_notices):
        raise ValueError("Outfit or JetBrains Mono original license is missing")

    yozai_source = local_path("blog/src/assets/fonts/Yozai-Medium.ttf")
    yozai_fingerprint = file_fingerprint(yozai_source)
    if yozai_fingerprint["sha256"] != "4db268ccf6e307859862052038e6f6326cce0190178a8ee88ca48aff6af1a06d":
        raise ValueError("Yozai font changed; re-inspect its source and license metadata before packaging")
    yozai_license_path = local_path("Yozai-OFL.txt")
    yozai_license = source_entry(yozai_license_path, "licenses/Yozai-OFL.txt")
    if yozai_license["sha256"] != "d53fbca0d78cec547dfb982cac815444044d79464288cd8db40f9fe125a45aa7":
        raise ValueError("Yozai OFL local bytes changed; review its source and normalization before packaging")
    yozai_provenance_path = local_path("evidence/Yozai-OFL-source.json")
    yozai_provenance = read_json(yozai_provenance_path)
    if yozai_provenance.get("url") != "https://raw.githubusercontent.com/lxgw/yozai-font/master/OFL.txt" or yozai_provenance.get("license") != "SIL Open Font License 1.1":
        raise ValueError("Yozai license source record differs from the inspected author source")
    normalization = "Author's official raw URL rendered by the web tool; tool line labels removed and blank lines follow rendered text. Local saved bytes are hashed; equality with original HTTP bytes is not asserted. No upstream commit was established."
    yozai_license["provenance"].update({"source_record": yozai_provenance_path.relative_to(RELEASE).as_posix(), "source_url": yozai_provenance["url"], "normalization": normalization, "upstream_byte_equality_asserted": False})
    entries.append(yozai_license)
    yozai_provenance_entry = source_entry(yozai_provenance_path, "licenses/Yozai-OFL-source.json")
    entries.append(yozai_provenance_entry)
    notices.append({"component": "Yozai Medium", "source": "Yozai-OFL.txt", "packaged_as": yozai_license["path"], **{key: yozai_license[key] for key in ("bytes", "sha256", "crc32")}, "normalization": normalization})
    materials = {
        "scope": "Known local license texts and font-source evidence, including the documented normalized Yozai author text; not a complete dependency audit or legal determination.",
        "notices": notices,
        "local_font_source_record": {"source": font_record_path.relative_to(RELEASE).as_posix(), **file_fingerprint(font_record_path), "files": rows},
        "yozai_source": {
            "component": "Yozai Medium", "source": yozai_source.relative_to(RELEASE).as_posix(), **yozai_fingerprint,
            "font_name_table_observation": "Version 0.863;May 27, 2025; Copyright 2020, 2024 LXGW (https://github.com/lxgw/yozai-font); Original Font Data Copyright (C) Y.OzVox.; name 13 declares SIL Open Font License 1.1 and links https://scripts.sil.org/OFL.",
            "holder_comparison": "The saved author OFL names LXGW and Y.Oz (Y.OzVox), consistent with the inspected font's copyright holders. This does not identify a font-release commit.",
            "license_path": yozai_license["path"], "license_sha256": yozai_license["sha256"], "normalization": normalization,
            "source_record": {"packaged_as": yozai_provenance_entry["path"], "sha256": yozai_provenance_entry["sha256"], "contents": yozai_provenance},
        },
        "known_missing_original_notices": [],
        "not_executed": ["license_download_by_packager", "legal_review", "complete_transitive_dependency_audit"],
    }
    materials_data = (json.dumps(materials, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    entries.append(generated_entry(materials_data, "licenses/第三方资料来源.json", {"kind": "generated_known_third_party_sources", "complete_license_set_claimed": False}))
    return entries, materials


def write_zip_entry(archive, entry, timestamp):
    info = zipfile.ZipInfo(entry["path"], timestamp)
    info.create_system = 3
    mode = 0o755 if entry["path"] == "deployment/switch-release.sh" else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    digest = hashlib.sha256()
    crc = 0
    count = 0
    with archive.open(info, "w", force_zip64=True) as target:
        if "_source" in entry:
            source_path = local_path(entry["_source"])
            with source_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(chunk)
                    digest.update(chunk)
                    crc = zlib.crc32(chunk, crc)
                    count += len(chunk)
        else:
            data = entry["_data"]
            target.write(data)
            digest.update(data)
            crc = zlib.crc32(data)
            count = len(data)
    if (count, digest.hexdigest(), f"{crc & 0xffffffff:08x}") != (entry["bytes"], entry["sha256"], entry["crc32"]):
        raise ValueError(f"Input changed during ZIP creation: {entry['path']}")


def verify_zip(archive, expected):
    infos = archive.infolist()
    if len(infos) != len(expected) or {info.filename for info in infos} != set(expected):
        raise ValueError("ZIP contains missing, additional or duplicate entries")
    total = 0
    for info in infos:
        safe_relative(info.filename)
        row = expected[info.filename]
        if info.is_dir() or info.flag_bits & 1 or not stat.S_ISREG(info.external_attr >> 16):
            raise ValueError(f"Unexpected directory/encryption/symlink in ZIP: {info.filename}")
        if info.file_size != row["bytes"] or info.CRC != int(row["crc32"], 16):
            raise ValueError(f"ZIP size/CRC differs from source: {info.filename}")
        digest = hashlib.sha256()
        crc = 0
        count = 0
        with archive.open(info, "r") as reader:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                count += len(chunk)
                digest.update(chunk)
                crc = zlib.crc32(chunk, crc)
        if (count, digest.hexdigest(), f"{crc & 0xffffffff:08x}") != (row["bytes"], row["sha256"], row["crc32"]):
            raise ValueError(f"ZIP decompressed bytes differ from source: {info.filename}")
        total += count
    return {"entries": len(infos), "uncompressed_bytes": total, "every_entry_sha256_and_crc32_verified": True}


def write_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)


def default_deployment_manifest():
    return next((name for name in ("deployment/DELIVERY-SHA256-v5.json", "deployment/DELIVERY-SHA256-v4.json") if (RELEASE / name).is_file()), "deployment/DELIVERY-SHA256-v3.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", required=True, help="Verified dist-NAME child of the release")
    parser.add_argument("--assembly-report", required=True, help="Existing successful assembly JSON under evidence/")
    parser.add_argument("--report", required=True, help="Existing final delivery report supplied by the coordinator")
    parser.add_argument("--build-guide", default="使用与构建说明.txt")
    parser.add_argument("--deployment-manifest", default=default_deployment_manifest())
    parser.add_argument("--package", required=True, help="New unique id, e.g. kuhai-20261022-v1")
    args = parser.parse_args()
    if not re.fullmatch(r"dist-[A-Za-z0-9_-]+", args.dist) or not re.fullmatch(r"kuhai-[A-Za-z0-9_-]{1,64}", args.package):
        raise ValueError("Use an explicit versioned dist-NAME and a portable kuhai-PACKAGE id")
    root = local_path(args.dist, directory=True)
    assembly_path = local_path(args.assembly_report)
    if assembly_path.parent != RELEASE / "evidence" or assembly_path.suffix != ".json":
        raise ValueError("Assembly evidence must be a JSON file directly under evidence/")
    # Missing final documents fail before creating any output directory or archive.
    documents = []
    for option, label in ((args.build_guide, "使用与构建说明"), (args.report, "本轮交付报告"), ("备案展示说明.txt", "备案展示说明")):
        path = local_path(option)
        if path.suffix.lower() not in {".txt", ".md", ".pdf"} or any(part.startswith(".") for part in path.relative_to(RELEASE).parts):
            raise ValueError("Human-facing delivery documents must be existing visible TXT/MD/PDF files")
        if path.stat().st_size == 0:
            raise ValueError(f"Human-facing delivery document is empty: {path}")
        documents.append((path, label + path.suffix.lower()))
    deployment_manifest_path = local_path(args.deployment_manifest)
    if deployment_manifest_path.parent != RELEASE / "deployment" or not re.fullmatch(r"DELIVERY-SHA256-v[0-9]+\.json", deployment_manifest_path.name):
        raise ValueError("Select a versioned current deployment manifest")
    package_parent = local_path("delivery-packages", directory=True, required=False)
    package_root = local_path(package_parent / args.package, directory=True, required=False)
    if package_root.exists() or redirected(package_root):
        raise FileExistsError(f"Refusing to overwrite package directory: {package_root}")

    assembly = read_json(assembly_path)
    if assembly.get("schema") != "kuhai-static-assembly-v1" or assembly.get("passed") is not True or assembly.get("output") != args.dist or assembly.get("origin") != "https://kuhaiyongcun.com" or assembly.get("blog_base") != "/blog/":
        raise ValueError("Assembly report does not approve this exact versioned dist")
    expected_dist = inventory_rows(assembly.get("files"))
    if assembly.get("files_count") != len(expected_dist) or assembly.get("total_bytes") != sum(row["bytes"] for row in expected_dist.values()):
        raise ValueError("Assembly inventory totals are inconsistent")
    preflight = assembly.get("preflight", {})
    preflight_path = local_path(preflight.get("path", ""))
    if preflight_path.parent != RELEASE / "evidence" or preflight.get("exit_code") != 0 or file_fingerprint(preflight_path)["sha256"] != preflight.get("sha256"):
        raise ValueError("Preflight evidence is missing, changed or failed")
    preflight_result = read_json(preflight_path)
    if preflight_result.get("passed") is not True or inventory_rows(preflight_result.get("files")) != expected_dist:
        raise ValueError("Preflight and assembly inventories disagree")
    paths = actual_files(root)
    if set(paths) != set(expected_dist):
        raise ValueError("Published files changed after assembly: added or missing files")
    for required in ("index.html", "blog/index.html", "404.html", "blog/404.html", "robots.txt", "sitemap-index.xml"):
        if required not in paths:
            raise ValueError(f"Incomplete static website: {required}")
    entries = [source_entry(paths[name], "dist/" + name, expected_dist[name]) for name in sorted(paths)]
    for path, archive_name in documents:
        entries.append(source_entry(path, archive_name))
    license_entries, third_party_materials = third_party_entries()
    entries.extend(license_entries)

    deployment_record = read_json(deployment_manifest_path)
    deployment_inventory = inventory_rows(deployment_record.get("files"))
    required_deployment = DEPLOYMENT_FILES + (("server-check.py",) if deployment_record.get("revision", 0) >= 4 else ())
    for relative in required_deployment:
        if relative not in deployment_inventory:
            raise ValueError(f"Deployment manifest omits required file: {relative}")
        path = local_path(RELEASE / "deployment" / relative)
        entry = source_entry(path, "deployment/" + relative, deployment_inventory[relative])
        if relative == "部署与更新说明.txt":
            text = path.read_text(encoding="utf-8-sig")
            source_sha = entry["sha256"]
            entry = generated_entry(portable_deployment_guide(text), entry["path"], {"kind": "portable_guide_copy", "source": "deployment/部署与更新说明.txt", "source_sha256": source_sha, "changes": "Removed old workspace evidence/status and old-manifest pointers; deployment instructions retained. Original workspace file untouched."})
        entries.append(entry)

    readme = (
        "主舰／档案室：离线静态部署包\n\n"
        "域名：https://kuhaiyongcun.com；作者：kuhai。\n"
        "只将 dist/ 的内容设为网站根目录。deployment/、licenses/、说明、交付报告及校验清单都留在 webroot 之外。\n"
        "部署步骤见 deployment/部署与更新说明.txt，目标是 Linux + Nginx；/ 为主舰，/blog/ 为完整博客。\n"
        "此包没有博客源码、site.json、node_modules 或构建运行时。根使用与构建说明描述作者原工作区的写作/构建流程，不能在这个静态包内直接运行那些源码命令。\n"
        "在解压前，从ZIP旁边运行 sha256sum -c SHA256SUMS.txt；解压到全新目录后，在解压根运行 sha256sum -c PAYLOAD-SHA256SUMS.txt。\n"
        "包中所有条目已经逐项回读并核对来源 SHA256 和 CRC32；这只证明离线文件完整性。\n"
        "没有连接服务器或部署。nginx -t、实际证书路径、TLS、正式域名HTTP/HTTPS、生产缓存/gzip/Range仍待服务器验收。\n"
        "浏览器、模型及备案完成情况只依据随包本轮交付报告；打包程序不会把待验项改成通过，不会生成备案号。\n"
        "备案接入规则见根备案展示说明。已找到的第三方原许可保存在 licenses/；来源及具体缺项见其中第三方资料来源.json，不表示所有依赖许可已核全。\n"
    )
    entries.append(generated_entry(readme.encode("utf-8"), "README-部署包.txt", {"kind": "generated_package_instructions"}))
    names = [entry["path"] for entry in entries]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Archive entry names collide")
    created = datetime.now(timezone.utc)
    manifest = {
        "schema": "kuhai-offline-deployment-package-v1", "created_utc": created.isoformat(), "package": args.package,
        "dist_source": args.dist, "webroot_in_archive": "dist/", "origin": "https://kuhaiyongcun.com", "author": "kuhai",
        "assembly_report": {"source": str(assembly_path.relative_to(RELEASE)), **file_fingerprint(assembly_path)},
        "preflight_report": {"source": str(preflight_path.relative_to(RELEASE)), **file_fingerprint(preflight_path)},
        "deployment_manifest": {"source": str(deployment_manifest_path.relative_to(RELEASE)), **file_fingerprint(deployment_manifest_path)},
        "files": [public_row(entry) for entry in entries],
        "payload_files_count": len(entries), "payload_bytes": sum(entry["bytes"] for entry in entries),
        "excluded": ["deployment/history/", "all previous deployment hash manifests", "deployment/交付状态.json", "source trees", "site.json", "hidden/private files", "source maps", "node_modules"],
        "server_validation": {"nginx_config_test": "PENDING_ON_ACTUAL_SERVER", "certificate_paths": "PLACEHOLDERS_REQUIRE_REAL_PATHS", "tls": "PENDING_ON_ACTUAL_SERVER", "deployment_executed": False},
        "browser_and_model_acceptance": "SEE_PROVIDED_DELIVERY_REPORT_NOT_INFERRED_BY_PACKAGER",
        "filing_approval": "NOT_ASSERTED_BY_PACKAGER",
        "third_party_materials": third_party_materials,
        "integrity_scope": "Files list covers payload; generated MANIFEST.json and PAYLOAD-SHA256SUMS.txt are also verified during ZIP readback. External SHA256SUMS.txt verifies ZIP and sidecar manifest.",
        "packager_sha256": file_fingerprint(Path(__file__))["sha256"],
    }
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_entry = generated_entry(manifest_data, "MANIFEST.json", {"kind": "generated_manifest"})
    checksum_data = ("".join(f"{entry['sha256']}  {entry['path']}\n" for entry in [*entries, manifest_entry])).encode("utf-8")
    entries.extend([manifest_entry, generated_entry(checksum_data, "PAYLOAD-SHA256SUMS.txt", {"kind": "generated_payload_checksums"})])
    expected_zip = {entry["path"]: public_row(entry) for entry in entries}
    evidence_root = local_path("evidence", directory=True)
    token = created.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    evidence_path = evidence_root / f"package-{args.package}-{token}.json"
    evidence = {"schema": "kuhai-offline-package-verification-v1", "created_utc": created.isoformat(), "package": args.package, "passed": False, "outputs": [], "not_executed": ["deployment", "SSH", "upload", "nginx_-t", "TLS", "browser", "filing_approval"]}
    package_parent.mkdir(exist_ok=True)
    package_root.mkdir()
    partial_path = package_root / (args.package + ".zip.partial")
    zip_path = package_root / (args.package + ".zip")
    try:
        with zipfile.ZipFile(partial_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for entry in entries:
                write_zip_entry(archive, entry, created.timetuple()[:6])
        with zipfile.ZipFile(partial_path, "r") as archive:
            evidence["zip_readback"] = verify_zip(archive, expected_zip)
        # Hard-link publication is atomic and never replaces an existing target.
        # On a filesystem without hard links, fail and retain the verified partial.
        os.link(partial_path, zip_path)
        partial_path.unlink()
        manifest_path = package_root / "MANIFEST.json"
        write_new(manifest_path, manifest_data)
        archive_hash = file_fingerprint(zip_path)
        outer_checksums = f"{archive_hash['sha256']}  {zip_path.name}\n{manifest_entry['sha256']}  MANIFEST.json\n"
        sums_path = package_root / "SHA256SUMS.txt"
        write_new(sums_path, outer_checksums.encode("utf-8"))
        for path in (zip_path, manifest_path, sums_path):
            evidence["outputs"].append({"path": str(path.relative_to(RELEASE)), **file_fingerprint(path)})
        evidence["source_files_and_generated_payloads_verified"] = len(entries)
        evidence["passed"] = True
    except Exception as error:
        evidence["error"] = f"{type(error).__name__}: {error}"
        evidence["retained_package_directory"] = str(package_root.relative_to(RELEASE))
    finally:
        write_new(evidence_path, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"passed": evidence["passed"], "package_directory": str(package_root), "evidence": str(evidence_path), "evidence_sha256": file_fingerprint(evidence_path)["sha256"], "error": evidence.get("error")}, ensure_ascii=False))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Packaging stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
