"""Build a NEW local static release. Never deploys, installs, or starts a server."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PLAN = "release-plan/p26p27-v1.json"
STATE = "release-plan/last-success.json"
LOCK = "release-plan/.release.lock"
SOURCE = {"stage": "P26-P27", "sha256": "dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339"}
SNAPSHOT_SHA = "cda83ceb10a1618c23789c14df59ad12cb9957e6e9ff603216f59a6e6485154a"
SNAPSHOT = "public-p26p27-final-20261022-r1/snapshot.json"
BLOG_STEPS = ("configure", "content-validate", "content-sync", "check", "type-check", "check-manifest", "build")
VERSION = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
SHA = re.compile(r"[0-9a-f]{64}")
ASSET_SUFFIXES = r"css|js|mjs|png|jpe?g|webp|avif|gif|svg|ico|woff2?|ttf|otf|wasm|glb|bin"
CONFIGURE_OUTPUTS = {"content/config/site.yaml", "content/config/profile.yaml", "content/config/footer.html"}
KNOWN_CONTENT_MARKERS = {"content/content/" + name + "/.keep" for name in ("moments", "posts", "series", "snippets")}
KNOWN_CONTENT_MARKER = {"bytes": 72, "sha256": "46e720f57bc8168731fdd20fd54e1a9548dec114949c3df7545cd0400850a970"}


def utc():
    return datetime.now(timezone.utc).isoformat()


def linked(path):
    try:
        reparse = getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
    except FileNotFoundError:
        return False
    return bool(reparse) or path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def relative_name(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\\:<>"|?*') or any(ord(c) < 32 for c in value):
        raise ValueError("Expected a safe release-relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts):
        raise ValueError("Empty, dot and parent path components are forbidden")
    if any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p, re.I) for p in parts):
        raise ValueError("Reserved filename")
    return PurePosixPath(value)


def local(root, value, required=True):
    supplied = Path(value)
    if supplied.is_absolute():
        try:
            value = supplied.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("Path must remain inside this release") from exc
    else:
        value = supplied.as_posix()
    rel = relative_name(value)
    candidate = root
    for part in rel.parts:
        candidate /= part
        if linked(candidate):
            raise ValueError("Symlink/junction paths are forbidden: " + rel.as_posix())
    if candidate.resolve(strict=required) != candidate:
        raise ValueError("Path alias is forbidden: " + rel.as_posix())
    return candidate


def fingerprint(path):
    before = path.stat()
    if linked(path) or not stat.S_ISREG(before.st_mode):
        raise ValueError("Expected a regular unlinked file")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("File changed while hashing: " + path.name)
    return {"bytes": after.st_size, "sha256": h.hexdigest()}


def load_json(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("JSON exceeds review bound")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_new(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(data)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def inventory(root, directory, hide_sensitive=True, excluded_files=(), excluded_prefixes=()):
    start = local(root, directory)
    if not start.is_dir():
        raise ValueError("Required source directory missing: " + str(directory))
    rows = {}
    folded = set()
    for parent, dirs, names in os.walk(start, followlinks=False):
        dirs.sort()
        for name in [*dirs, *sorted(names)]:
            p = Path(parent) / name
            rel = p.relative_to(start).as_posix()
            release_rel = p.relative_to(root).as_posix()
            if release_rel in excluded_files or any(release_rel.startswith(prefix) or release_rel + "/" == prefix for prefix in excluded_prefixes):
                if name in dirs:
                    dirs.remove(name)
                continue
            relative_name(rel)
            if linked(p):
                raise ValueError("Linked file/directory in input: " + rel)
            marker_row = None
            if hide_sensitive and name in {".keep", ".gitkeep"}:
                placeholder = p.lstat()
                if not stat.S_ISREG(placeholder.st_mode):
                    raise ValueError("Only regular .keep/.gitkeep placeholders are allowed; not read: " + rel)
                # Empty directory markers contain no author data and are not
                # inputs to the website. Do not relax any other hidden path.
                if placeholder.st_size == 0:
                    continue
                # These four reviewed source markers contain a fixed public
                # explanation. Keep their bytes in the input inventory so a
                # later change cannot silently become an allowed hidden file.
                if release_rel not in KNOWN_CONTENT_MARKERS or placeholder.st_size != KNOWN_CONTENT_MARKER["bytes"]:
                    raise ValueError("Unknown nonempty .keep/.gitkeep placeholder; not read: " + rel)
                marker_row = fingerprint(p)
                if marker_row != KNOWN_CONTENT_MARKER:
                    raise ValueError("Known content placeholder changed: " + rel)
            elif hide_sensitive and (name.startswith(".") or name.lower().endswith((".pem", ".key"))):
                raise ValueError("Unexpected hidden/private input; not read: " + rel)
            if p.is_dir():
                continue
            local(root, p)
            if rel.casefold() in folded:
                raise ValueError("Case-colliding source files")
            folded.add(rel.casefold())
            rows[rel] = marker_row if marker_row is not None else fingerprint(p)
    return rows


def file_rows(rows):
    result = {}
    folded = set()
    if not isinstance(rows, list) or not rows:
        raise ValueError("A non-empty inventory is required")
    for row in rows:
        name = relative_name(row["path"]).as_posix()
        if name.casefold() in folded or type(row.get("bytes")) is not int or row["bytes"] < 0 or not SHA.fullmatch(row.get("sha256", "")):
            raise ValueError("Invalid inventory row")
        folded.add(name.casefold())
        result[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    return result


def shared_inputs(root, plan):
    """Only named public source/config paths; never scan environment/credential files."""
    rows = {}
    for value in plan["sharedInputFiles"]:
        path = local(root, value, required=False)
        rows[value] = fingerprint(path) if path.exists() else None
    for value in plan["sharedInputDirectories"]:
        for name, row in inventory(root, value, excluded_files=plan.get("sharedInputExcludedFiles", []), excluded_prefixes=plan.get("sharedInputExcludedPrefixes", [])).items():
            full_name = value + "/" + name
            rows[full_name] = row
    return dict(sorted(rows.items()))


def after_configure(selected, actual):
    changed = {name for name in set(selected) | set(actual) if selected.get(name) != actual.get(name)}
    unexpected = sorted(changed - CONFIGURE_OUTPUTS)
    if unexpected:
        raise RuntimeError("Shared input changed during configure; only its three generated config files may change: " + ", ".join(unexpected[:8]))
    return actual


def validate_ship(root, record, expected_site=None):
    manifest_path = local(root, record["manifest"])
    if fingerprint(manifest_path)["sha256"] != record["manifestSha256"]:
        raise ValueError("Pinned ship manifest changed")
    manifest = load_json(manifest_path)
    directory = relative_name(record["directory"])
    if directory.parent.as_posix() != "ship" or not re.fullmatch(r"dist(?:-[A-Za-z0-9_-]+)?", directory.name):
        raise ValueError("Ship directory must be a direct ship/dist-NAME child")
    if manifest.get("schema") != "ship-release-build-v1" or manifest.get("sourceStage") != SOURCE["stage"] or manifest.get("sourceSceneSha256") != SOURCE["sha256"] or manifest.get("snapshot") != SNAPSHOT or manifest.get("snapshotSha256") != SNAPSHOT_SHA or manifest.get("output") != directory.name:
        raise ValueError("Ship manifest does not identify the pinned P26-P27 source")
    if expected_site and manifest.get("siteConfigSha256") != expected_site:
        raise ValueError("Ship footer/config is stale; shared rebuild required")
    if inventory(root, record["directory"]) != file_rows(manifest["assets"]):
        raise ValueError("Ship build changed since its manifest")
    return manifest


def validate_plan(root, plan):
    if plan.get("schema") != "kuhai-local-release-plan-v1" or plan.get("source") != SOURCE or plan.get("snapshot") != SNAPSHOT or plan.get("snapshotSha256") != SNAPSHOT_SHA:
        raise ValueError("Release plan must explicitly pin the reviewed P26-P27 snapshot")
    snapshot_path = local(root, "ship/" + plan["snapshot"])
    if fingerprint(snapshot_path)["sha256"] != SNAPSHOT_SHA:
        raise ValueError("Pinned snapshot changed; no P25 fallback is permitted")
    snapshot = load_json(snapshot_path)
    if snapshot.get("source") != SOURCE:
        raise ValueError("Snapshot source mismatch")
    manifest = validate_ship(root, plan["baselineShip"])
    # Runtime assets and the small geometry/protection/reference evidence are immutable.
    for row in manifest["assets"]:
        if row["path"].startswith("assets/"):
            path = local(root, snapshot_path.parent / relative_name(row["path"]))
            if fingerprint(path) != {key: row[key] for key in ("bytes", "sha256")}:
                raise ValueError("Snapshot runtime asset changed: " + row["path"])
    for row in snapshot["evidence"]:
        if row.get("kind") not in {"geometry", "protection", "same-camera"}:
            raise ValueError("Unexpected snapshot evidence kind")
        # The importer stores evidence by kind; row.path names its original
        # handoff location, not its location inside the copied snapshot.
        path = local(root, snapshot_path.parent / "handoff-evidence" / (row["kind"] + ".report"))
        if fingerprint(path) != {key: row[key] for key in ("bytes", "sha256")}:
            raise ValueError("Snapshot evidence changed: " + row["path"])
    handoff_path = local(root, snapshot_path.parent / "handoff-evidence/handoff.json")
    if fingerprint(handoff_path)["sha256"] != snapshot.get("handoffSha256"):
        raise ValueError("Copied snapshot handoff identity changed")
    if not isinstance(plan.get("baselineSharedInputs"), dict) or not plan["baselineSharedInputs"]:
        raise ValueError("Baseline source fingerprint has not been frozen")


def choose_mode(requested, expected, actual):
    changed = sorted(name for name in set(expected) | set(actual) if expected.get(name) != actual.get(name))
    if requested == "articles" and changed:
        raise ValueError("articles cannot reuse a ship after shared source/config changes; use --mode shared (" + ", ".join(changed[:8]) + ")")
    return ("shared" if requested == "shared" or changed else "articles"), changed


@contextlib.contextmanager
def exclusive_lock(root, version):
    path = local(root, LOCK, required=False)
    path.parent.mkdir(exist_ok=True)
    token = uuid.uuid4().hex
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"token": token, "pid": os.getpid(), "version": version, "createdUTC": utc()}, stream)
    except FileExistsError as exc:
        raise RuntimeError("Another release owns the lock. Do not remove an active or unverified stale lock.") from exc
    try:
        yield token
    finally:
        # Never erase another process's replacement lock or auto-break a stale lock.
        if path.is_file() and not linked(path) and load_json(path).get("token") == token:
            path.unlink()


def validate_assembly(root, record):
    path = local(root, record["path"])
    if path.parent != root / "evidence" or path.suffix != ".json":
        raise ValueError("Assembly must be directly under evidence/")
    if record.get("sha256") and fingerprint(path)["sha256"] != record["sha256"]:
        raise ValueError("Previous assembly identity changed")
    value = load_json(path)
    if value.get("schema") != "kuhai-static-assembly-v1" or value.get("passed") is not True or value.get("origin") != "https://kuhaiyongcun.com" or value.get("blog_base") != "/blog/" or not re.fullmatch(r"dist-[A-Za-z0-9_-]+", value.get("output", "")):
        raise ValueError("Previous assembly is not a passed local release")
    directory = local(root, value["output"])
    # .well-known is a legitimate public directory; publication checks run separately.
    if inventory(root, value["output"], hide_sensitive=False) != file_rows(value["files"]):
        raise ValueError("Previous dist no longer matches its assembly")
    return value, directory


def hashed_asset(name):
    """Conservative supported build naming, never HTML/JSON/unhashed resources."""
    relative_name(name)
    if any(part.startswith(".") for part in name.split("/")):
        return False
    if re.match(r"(?:sw|service[-_]?worker)(?:[._-]|$)", PurePosixPath(name).name, re.I):
        return False
    if re.search(r"\.[0-9a-f]{8,64}\.(?:" + ASSET_SUFFIXES + r")$", name, re.I):
        return True
    if re.fullmatch(r"(?:blog/)?_astro/[^/]+\.[A-Za-z0-9_-]{8,}\.(?:" + ASSET_SUFFIXES + r")", name):
        return True
    return bool(re.fullmatch(r"chunks/[^/]+-[A-Z0-9]{8}\.(?:js|css)(?:\.LEGAL\.txt)?", name))


def retain_hashed_assets(root, old, destination):
    report = {"copied": [], "already_present": [], "unhashed_files_not_copied": 0,
              "scope": "Only verified content-hash filenames. No old HTML, JSON, service worker or unhashed runtime copied. Unhashed URL continuity is not certified."}
    if old is None:
        report["status"] = "NO_PREVIOUS_DIST_AVAILABLE"
        return report
    assembly, source = old
    report.update(status="CHECKED", previous_dist=assembly["output"])
    for name, expected in file_rows(assembly["files"]).items():
        if not hashed_asset(name):
            report["unhashed_files_not_copied"] += 1
            continue
        src = local(root, source / relative_name(name))
        dst = local(root, destination / relative_name(name), required=False)
        if fingerprint(src) != expected:
            raise ValueError("Previous asset changed during retention")
        if dst.exists():
            if fingerprint(dst) != expected:
                raise ValueError("Content-hash URL collision; refusing overwrite: " + name)
            report["already_present"].append(name)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as reader, dst.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
        if fingerprint(dst) != expected:
            raise ValueError("Retained asset differs from verified previous bytes")
        report["copied"].append({"path": name, **expected})
    return report


def import_script(root, filename, name):
    path = local(root, "scripts/" + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def previous_release(root, plan, state, supplied):
    if supplied:
        return validate_assembly(root, {"path": supplied})
    if state:
        return validate_assembly(root, state["assembly"])
    optional = plan.get("baselineAssembly")
    if optional:
        path = local(root, optional["path"], required=False)
        if path.is_file():
            value = load_json(path)
            directory = local(root, value["output"], required=False)
            if directory.is_dir():
                return validate_assembly(root, optional)
    # A restored developer bundle intentionally need not contain the old whole-site dist.
    return None


def select_deployment_manifest(root, plan, override=None):
    current = ("deployment/DELIVERY-SHA256-v5.json", "deployment/DELIVERY-SHA256-v4.json")
    selected = override or next((name for name in current if local(root, name, required=False).is_file()), plan["deploymentManifest"])
    path = local(root, selected)
    if path.parent != root / "deployment" or not re.fullmatch(r"DELIVERY-SHA256-v[0-9]+\.json", path.name):
        raise ValueError("Expected a versioned deployment manifest")
    for name, expected in file_rows(load_json(path).get("files")).items():
        if fingerprint(local(root, "deployment/" + name)) != expected:
            raise ValueError("Deployment input differs: " + name)
    return {"path": path.relative_to(root).as_posix(), **fingerprint(path)}


def plan_release(root, version, requested, previous, build_guide="开发与发布说明-v2.txt", deployment_manifest=None):
    if not VERSION.fullmatch(version):
        raise ValueError("Version must use 1–48 lowercase ASCII letters/digits/_/-, starting alphanumeric")
    plan_path = local(root, PLAN)
    plan = load_json(plan_path)
    validate_plan(root, plan)
    delivery = select_deployment_manifest(root, plan, deployment_manifest)
    state_path = local(root, STATE, required=False)
    state = load_json(state_path) if state_path.is_file() else None
    if state and (state.get("schema") != "kuhai-local-release-state-v1" or state.get("source") != SOURCE or state.get("snapshotSha256") != SNAPSHOT_SHA):
        raise ValueError("Last-success state refers to an unsupported baseline")
    actual = shared_inputs(root, plan)
    expected = state["sharedInputs"] if state else plan["baselineSharedInputs"]
    mode, changes = choose_mode(requested, expected, actual)
    ship = state["ship"] if state else plan["baselineShip"]
    if mode == "articles":
        validate_ship(root, ship, fingerprint(local(root, "site.json"))["sha256"])
    version_paths = {"dist": "dist-" + version, "shipDist": "ship/dist-" + version,
                     "shipManifest": "ship/build-manifest-dist-" + version + ".json",
                     "runDirectory": "evidence/release-" + version,
                     "report": "evidence/release-" + version + "-report.txt",
                     "finalAssembly": "evidence/assembly-dist-" + version + "-release.json",
                     "finalPreflight": "evidence/assembly-dist-" + version + "-release-preflight.json",
                     "packageDirectory": "delivery-packages/kuhai-" + version}
    for key, value in version_paths.items():
        if key in {"shipDist", "shipManifest"} and mode == "articles":
            continue
        if local(root, value, required=False).exists():
            raise FileExistsError("Version output already exists: " + value)
    if local(root, LOCK, required=False).exists():
        raise RuntimeError("Release lock exists; check its owner before continuing")
    old = previous_release(root, plan, state, previous)
    guide_path = local(root, build_guide)
    if guide_path.suffix.lower() not in {".txt", ".md", ".pdf"} or not guide_path.is_file() or not guide_path.stat().st_size:
        raise ValueError("Existing non-empty build guide required")
    return plan, {"schema": "kuhai-local-release-run-v1", "version": version, "createdUTC": utc(),
                  "mode": mode, "requestedMode": requested, "sharedChanges": changes,
                  "source": SOURCE, "snapshot": plan["snapshot"], "snapshotSha256": SNAPSHOT_SHA,
                  "plan": {"path": PLAN, **fingerprint(plan_path)}, "deploymentManifest": delivery, "paths": version_paths,
                  "ship": ship, "selectionInputs": actual, "buildGuide": guide_path.relative_to(root).as_posix(),
                  "previousDist": old[0]["output"] if old else None,
                  "previousAssetBoundary": "If updating an already deployed site without its previous dist, pass --previous-assembly with that locally verified release; no continuity is inferred.",
                  "steps": [], "passed": False, "notExecuted": ["deployment", "installation", "server_start", "browser", "nginx_-t", "TLS", "filing_approval"]}, old


class Runner:
    def __init__(self, root, record, environment):
        self.root, self.record, self.environment = root, record, environment

    def step(self, label, argv, cwd=None, output=None):
        log = local(self.root, output or self.record["paths"]["runDirectory"] + "/" + label + ".log", required=False)
        row = {"name": label, "argv": [str(arg) for arg in argv], "cwd": str((cwd or self.root).relative_to(self.root)) or ".", "startedUTC": utc(), "log": log.relative_to(self.root).as_posix()}
        self.record["steps"].append(row)
        print(json.dumps({"step": label, "log": row["log"]}), flush=True)
        interrupted = False
        with log.open("x", encoding="utf-8", newline="\n") as stream:
            process = subprocess.Popen([str(arg) for arg in argv], cwd=cwd or self.root, env=self.environment,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # Keep the exclusive lock while the current owned step saves/exits.
            # Do not orphan a run-pnpm child by releasing the lock on Ctrl+C.
            while True:
                try:
                    code = process.wait()
                    break
                except KeyboardInterrupt:
                    interrupted = True
                    print("Stop requested; waiting for the current owned step to exit, then no further step will start.", flush=True)
        row.update(exitCode=code, finishedUTC=utc(), interrupted=interrupted, **fingerprint(log))
        if code or interrupted:
            raise RuntimeError(f"Step {label} stopped ({code}, interrupted={interrupted}); log and partial outputs retained")
        return log


def last_json(path):
    # Assembly/packager print a small final JSON line, not their complete inventories.
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        lines = stream.read().decode("utf-8").splitlines()
    return json.loads(lines[-1])


def write_report(root, record, runtime):
    assembly = record["assembly"]
    message = (
        f"主舰／档案室：本地发布 {record['version']}\n\n"
        f"日期：{utc()}；分支：{record['mode']}。只生成新静态交付包，没有部署或启动服务。\n"
        f"域名：https://kuhaiyongcun.com；作者与备案以本次 site.json 构建后的真实页面为准。\n"
        f"固定阶段：{SOURCE['stage']}；源母版 SHA256：{SOURCE['sha256']}。\n"
        f"快照：ship/{record['snapshot']}；SHA256：{SNAPSHOT_SHA}。\n"
        f"主舰构建：{record['ship']['directory']}；清单：{record['ship']['manifest']}；SHA256：{record['ship']['manifestSha256']}。\n"
        f"组合目录：{record['paths']['dist']}；清单：{assembly['path']}；SHA256：{assembly['sha256']}。\n"
        f"实际静态文件：{assembly['files_count']} 件，{assembly['total_bytes']} 字节。\n"
        f"源配置变化：{json.dumps(record['sharedChanges'], ensure_ascii=False)}。\n"
        "博客 configure、内容与源码检查、构建、组合资源检查、preflight、公开元数据扫描均按本轮日志记录执行；任何失败会停止，不会跳过后封包。\n"
        "本轮没有启动浏览器或重跑视觉/触控/性能验收；源码或界面变化后需按影响补验。复用固定主舰只证明其文件未变，历史浏览器结果不改写为本轮结果。\n"
        "RESERVED 仍封闭；其它八类规划舱室未因本次发布装舰；本工具不制作或重新认证几何。\n"
        "只公开包内 dist。deployment、licenses、说明与清单留在 webroot 外。静态包不含源码，继续写作需保留开发包及固定快照。\n"
        "备案开关只使用作者实际配置；校验/构建成功不证明主管部门批准。未获批时保持关闭，不能填申请编号冒充完整核发号码。\n"
        f"旧哈希资源：{record['retention']['status']}，补入 {len(record['retention']['copied'])} 件；未哈希URL连续性、旧HTML/JSON不在保留范围。\n"
        "服务器 nginx -t、权限、证书、TLS、公网HTTP、缓存/gzip/Range及上线/回滚仍待真实服务器验证。\n"
        f"运行时版本：{json.dumps(runtime.versions, ensure_ascii=False)}；版本提示：{json.dumps(runtime.warnings, ensure_ascii=False)}。\n"
        f"本轮日志与机器清单：{record['paths']['runDirectory']}/run.json。该清单在封包后写入，包内不含它。\n"
        "本报告在封包前生成；实际ZIP完整性和路径以随后产生的 evidence/package-* 及其输出SHA256为准，未预先宣称封包成功。\n"
    )
    path = local(root, record["paths"]["report"], required=False)
    write_new(path, message)
    return {"path": path.relative_to(root).as_posix(), **fingerprint(path)}


def execute(root, plan, record, old, runtime, helper):
    with exclusive_lock(root, record["version"]) as token:
        directory = local(root, record["paths"]["runDirectory"], required=False)
        directory.mkdir()  # Version collision remains fatal, including a previous failure.
        environment = helper.controlled_environment(runtime, root, max_old_space_size=2048)
        environment["KUHAI_RELEASE_OWNER"] = token
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        runner = Runner(root, record, environment)
        python = [sys.executable, "-B"]
        try:
            if shared_inputs(root, plan) != record["selectionInputs"]:
                raise RuntimeError("Shared inputs changed after mode selection; run a fresh version")
            for mode in BLOG_STEPS:
                runner.step("blog-" + mode, [*python, root / "scripts/run-pnpm.py", mode])
                if mode == "configure":
                    settled = after_configure(record["selectionInputs"], shared_inputs(root, plan))
                    content = inventory(root, "content")
            if shared_inputs(root, plan) != settled or inventory(root, "content") != content:
                raise RuntimeError("Source content/config changed during the release; retained output is not published")
            if record["mode"] == "shared":
                runner.step("ship-build", [runtime.node, "--max-old-space-size=384", root / "ship/build.mjs",
                            "--out=" + Path(record["paths"]["shipDist"]).name,
                            "--snapshot=" + plan["snapshot"], "--snapshot-sha256=" + SNAPSHOT_SHA])
                manifest_path = local(root, record["paths"]["shipManifest"])
                record["ship"] = {"directory": record["paths"]["shipDist"], "manifest": record["paths"]["shipManifest"], "manifestSha256": fingerprint(manifest_path)["sha256"]}
            validate_ship(root, record["ship"], fingerprint(local(root, "site.json"))["sha256"])
            log = runner.step("assemble", [*python, root / "scripts/assemble.py", "--ship-dist", record["ship"]["directory"], "--blog-dist", "blog/dist", "--out", record["paths"]["dist"]])
            assembled = last_json(log)
            if assembled.get("passed") is not True:
                raise RuntimeError("Assembler did not affirm success")
            assembly_path = local(root, assembled["evidence"])
            assembly = load_json(assembly_path)
            destination = local(root, record["paths"]["dist"])
            record["retention"] = retain_hashed_assets(root, old, destination)
            if record["retention"]["copied"]:
                original = {"path": assembly_path.relative_to(root).as_posix(), **fingerprint(assembly_path)}
                preflight_path = runner.step("final-preflight", [*python, root / "deployment/preflight.py", destination], output=record["paths"]["finalPreflight"])
                checked = load_json(preflight_path)
                if checked.get("passed") is not True:
                    raise RuntimeError("Final retained-assets preflight did not pass")
                assembler = import_script(root, "assemble.py", "kuhai_release_assembler")
                assembly.update(created_at=utc(), original_assembly=original, asset_retention=record["retention"],
                                asset_check=assembler.verify_assets(destination), files=checked["files"], files_count=checked["files_count"], total_bytes=checked["total_bytes"],
                                preflight={"path": preflight_path.relative_to(root).as_posix(), "exit_code": 0, "sha256": fingerprint(preflight_path)["sha256"], "checker_sha256": fingerprint(root / "deployment/preflight.py")["sha256"], "stderr": ""},
                                release_coordinator_sha256=fingerprint(Path(__file__))["sha256"])
                assembly_path = local(root, record["paths"]["finalAssembly"], required=False)
                write_new(assembly_path, json_text(assembly))
            record["assembly"] = {"path": assembly_path.relative_to(root).as_posix(), **fingerprint(assembly_path), "files_count": assembly["files_count"], "total_bytes": assembly["total_bytes"]}
            metadata_path = runner.step("public-metadata", [*python, root / "scripts/audit-public-metadata.py", "--root", record["paths"]["dist"]])
            metadata = load_json(metadata_path)
            if metadata.get("passed") is not True:
                raise RuntimeError("Public metadata did not affirm success")
            record["metadata"] = {"path": metadata_path.relative_to(root).as_posix(), **fingerprint(metadata_path), "issues_count": metadata["issues_count"]}
            if shared_inputs(root, plan) != settled or inventory(root, "content") != content:
                raise RuntimeError("Source changed before packaging")
            record["sharedInputs"] = settled
            record["report"] = write_report(root, record, runtime)
            if select_deployment_manifest(root, plan, record["deploymentManifest"]["path"]) != record["deploymentManifest"]:
                raise RuntimeError("Deployment manifest changed during release")
            package_log = runner.step("package", [*python, root / "scripts/package-delivery.py", "--dist", record["paths"]["dist"], "--assembly-report", record["assembly"]["path"], "--report", record["report"]["path"], "--build-guide", record["buildGuide"], "--deployment-manifest", record["deploymentManifest"]["path"], "--package", "kuhai-" + record["version"]])
            packaged = last_json(package_log)
            if packaged.get("passed") is not True:
                raise RuntimeError("Packager did not affirm success")
            package_path = local(root, packaged["evidence"])
            package_evidence = load_json(package_path)
            if package_evidence.get("passed") is not True:
                raise RuntimeError("Package evidence did not affirm success")
            record["package"] = {"path": package_path.relative_to(root).as_posix(), **fingerprint(package_path), "outputs": package_evidence["outputs"]}
            # State is only a local pointer, never a substitute for pinned manifests.
            state = {"schema": "kuhai-local-release-state-v1", "source": SOURCE, "snapshotSha256": SNAPSHOT_SHA, "version": record["version"], "sharedInputs": settled, "ship": record["ship"], "assembly": record["assembly"], "package": record["package"]}
            temporary = local(root, "release-plan/last-success-" + token + ".tmp", required=False)
            write_new(temporary, json_text(state))
            state_path = local(root, STATE, required=False)
            os.replace(temporary, state_path)
            record["passed"] = True
        except Exception as error:
            record["error"] = type(error).__name__ + ": " + str(error)
        finally:
            record["finishedUTC"] = utc()
            write_new(directory / "run.json", json_text(record))
        print(json.dumps({"passed": record["passed"], "mode": record["mode"], "run": str(directory / "run.json"), "package": record.get("package"), "error": record.get("error")}, ensure_ascii=True), flush=True)
        return 0 if record["passed"] else 1


def main():
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required, including --check-only; no runtime is installed automatically")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mode", choices=("auto", "articles", "shared"), default="auto")
    parser.add_argument("--check-only", action="store_true", help="Read-only preflight and plan; no lock/log/build/output")
    parser.add_argument("--previous-assembly", help="Passed previous local assembly for old hashed-asset retention")
    parser.add_argument("--build-guide", default="开发与发布说明-v2.txt", help="Existing public developer guide to include outside webroot")
    parser.add_argument("--deployment-manifest", help="Versioned deployment manifest override; default v5, then v4, otherwise frozen-plan version")
    args = parser.parse_args()
    plan, record, old = plan_release(ROOT, args.version, args.mode, args.previous_assembly, args.build_guide, args.deployment_manifest)
    helper = import_script(ROOT, "runtime_paths.py", "kuhai_release_runtime")
    runtime = helper.resolve_runtime(ROOT)
    record["runtime"] = {"versions": runtime.versions, "sources": runtime.sources, "warnings": runtime.warnings}
    if args.check_only:
        record["checkOnly"] = True
        record["stepsPlanned"] = ["blog-" + step for step in BLOG_STEPS] + (["ship-build (explicit P26-P27 snapshot)"] if record["mode"] == "shared" else []) + ["assemble", "retain verified old hash assets", "public-metadata", "package with ZIP SHA/CRC readback"]
        summary = {key: value for key, value in record.items() if key != "selectionInputs"}
        summary["sharedInputFilesChecked"] = len(record["selectionInputs"])
        summary["sharedInputInventorySha256"] = hashlib.sha256(json_text(record["selectionInputs"]).encode("utf-8")).hexdigest()
        print(json_text(summary))
        return 0
    return execute(ROOT, plan, record, old, runtime, helper)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print("Release stopped: " + str(error), file=sys.stderr)
        raise SystemExit(1)
