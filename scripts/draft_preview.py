"""Build and serve a private, isolated Shirone draft snapshot. Never publishes or installs."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

import release as release_tools
from runtime_paths import controlled_environment, resolve_runtime, subprocess_flags

ROOT = Path(__file__).resolve().parents[1]
MARKER = "PREVIEW-ONLY.json"
RECEIPT = "draft-preview-receipt.json"
RECEIPT_SCHEMA = "kuhai-draft-preview-receipt-v1"
DEFAULT_ORIGIN = "http://127.0.0.1:4180"
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
PACKAGE = re.compile(r"(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+", re.I)
DENIED_NAME = re.compile(r"(?:[.]env(?:[.].*)?|[.]npmrc|[.]git|credentials|id_rsa|id_ed25519)", re.I)
BLOG_FILES = ("astro.config.mjs", "package.json", "tsconfig.json", "svelte.config.js", "pagefind.yml", "shirone.content.json")
BLOG_TREES = ("src", "scripts", "public")
SKIP_PREFIXES = ("src/content", "src/user", "src/assets/fonts/.subset", "src/generated")
STATE = "preview-work/preview-active.json"
SERVER_LOCK = "preview-work/.draft-server.lock"
CONTROL_LOCK = "preview-work/.draft-control.lock"


def utc():
    return datetime.now(timezone.utc).isoformat()


def safe_name(value, label="name"):
    if not isinstance(value, str) or not NAME.fullmatch(value) or re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])", value, re.I):
        raise ValueError(f"Invalid {label}; use 1–48 lowercase ASCII letters, digits, - or _")
    return value


def local(root, name, required=True):
    return release_tools.local(root, name, required=required)


def atomic_json(path, data):
    if release_tools.linked(path):
        raise ValueError("Linked record is forbidden")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def marker(version):
    return {"schema": "kuhai-draft-preview-marker-v1", "previewOnly": True, "version": version,
            "warning": "Private local draft preview. Must never be assembled, packaged or deployed."}


def write_marker(folder, version):
    path = folder / MARKER
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(marker(version), ensure_ascii=False, indent=2) + "\n")


def safe_files(root, relative, skip=()):
    """Enumerate ordinary source files without opening credentials or following links."""
    start = local(root, relative)
    rows = {}
    for directory, dirs, files in os.walk(start, followlinks=False):
        for name in sorted([*dirs, *files]):
            p = Path(directory) / name
            rel = p.relative_to(start).as_posix()
            if DENIED_NAME.fullmatch(name):
                raise ValueError("Private/config filename is not a preview input: " + rel)
            if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip):
                if name in dirs:
                    dirs.remove(name)
                continue
            if name.startswith(".") and name not in (".keep", ".gitkeep"):
                if name in dirs:
                    dirs.remove(name)
                continue
            if re.search(r"(?:^|[.])(?:pem|key|p12|pfx)$", name, re.I):
                raise ValueError("Private-looking file is not a preview input: " + rel)
            if release_tools.linked(p):
                raise ValueError("Linked preview source is forbidden: " + rel)
            if p.is_file():
                rows[p.relative_to(root).as_posix()] = release_tools.fingerprint(p)
            elif not p.is_dir():
                raise ValueError("Non-regular preview input: " + rel)
    return rows


def source_inventory(root, slug):
    rows = {}
    for directory in ("content", f"authoring-private/{slug}"):
        rows.update(safe_files(root, directory))
    for directory in BLOG_TREES:
        rows.update(safe_files(root, "blog/" + directory, skip=("assets/fonts/.subset", "generated") if directory == "src" else ()))
    for relative in [*("blog/" + x for x in BLOG_FILES), "site.json", "scripts/filing.mjs"]:
        rows[relative] = release_tools.fingerprint(local(root, relative))
    for relative in ("release-plan/last-success.json",):
        path = local(root, relative, required=False)
        rows[relative] = release_tools.fingerprint(path) if path.exists() else None
    # Protect the last ordinary blog output as well as author inputs.
    if local(root, "blog/dist", required=False).exists():
        rows.update(safe_files(root, "blog/dist"))
    return rows


def copy_inputs(root, snapshot):
    public = local(root, "content/public")
    owned_public = {p.name for p in public.iterdir() if not p.name.startswith(".")}
    rows = {}
    for directory in BLOG_TREES:
        skip = tuple(x.removeprefix(directory + "/") for x in SKIP_PREFIXES if x.startswith(directory + "/"))
        if directory == "public":
            skip += tuple(sorted(owned_public))
        rows.update(safe_files(root, "blog/" + directory, skip=skip))
    for relative in [*("blog/" + x for x in BLOG_FILES), "site.json", "scripts/filing.mjs"]:
        rows[relative] = release_tools.fingerprint(local(root, relative))
    for relative, expected in rows.items():
        source = local(root, relative)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        if release_tools.fingerprint(target) != expected:
            raise ValueError("Source changed during snapshot copy: " + relative)
    for relative in ("blog/src/content", "blog/src/user", "blog/src/generated", "blog/public/assets"):
        (snapshot / relative).mkdir(parents=True, exist_ok=True)
    # Configuration wrapping happens only in the copied project.
    config = snapshot / "blog/astro.config.mjs"
    config.rename(config.with_name("astro.original.config.mjs"))
    config.write_text('import { fileURLToPath } from "node:url";\nimport original from "./astro.original.config.mjs";\n'
                      'export default { ...original, cacheDir: fileURLToPath(new URL("./.draft-cache/astro/", import.meta.url)),\n'
                      '  vite: { ...original.vite, cacheDir: fileURLToPath(new URL("./.draft-cache/vite/", import.meta.url)) } };\n', encoding="utf-8")
    return rows


def create_directory_link(source, target):
    if target.exists() or target.is_symlink():
        raise ValueError("Dependency link target already exists")
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(source), str(target))
    else:
        target.symlink_to(source, target_is_directory=True)


def dependency_facade(root, snapshot):
    original = local(root, "blog/node_modules")
    destination = snapshot / "blog/node_modules"
    destination.mkdir()
    links = []
    packages = []
    for entry in sorted(original.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name.startswith("@"):
            if release_tools.linked(entry):
                raise ValueError("Scoped dependency container must be a real directory")
            packages.extend(sorted(entry.iterdir()))
        else:
            packages.append(entry)
    for package in packages:
        name = package.relative_to(original).as_posix()
        if not PACKAGE.fullmatch(name) or any(part in (".", "..") for part in name.split("/")):
            raise ValueError("Unexpected installed package name")
        actual = package.resolve(strict=True)
        if not actual.is_relative_to(original) or not actual.is_dir():
            raise ValueError("Installed package escapes this author's node_modules: " + name)
        if not (actual / "package.json").is_file():
            raise ValueError("Installed package has no package.json: " + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        create_directory_link(actual, target)
        links.append({"package": name, "target": actual.relative_to(root).as_posix()})
    for required in ("astro", "pagefind", "yaml"):
        if not (destination / required / "package.json").is_file():
            raise ValueError("Required installed dependency missing: " + required)
    return links


def cli_entry(root, package, name):
    modules = local(root, "blog/node_modules")
    directory = (modules / package).resolve(strict=True)
    if not directory.is_relative_to(modules):
        raise ValueError("CLI package escapes installed dependency root")
    data = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    value = data.get("bin")
    value = value.get(name) if isinstance(value, dict) else value
    if not isinstance(value, str):
        raise ValueError("Installed package has no requested CLI")
    entry = (directory / value).resolve(strict=True)
    if not entry.is_relative_to(directory) or not entry.is_file():
        raise ValueError("Installed CLI escapes its package")
    return entry


def wait_owned_writer(child):
    """Do not orphan a writer or its native work by releasing its build lock."""
    while child.poll() is None:
        try:
            child.wait(timeout=1)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            continue


def execute(command, cwd, environment, log, timeout=900):
    """Wait for the owned child before releasing the shared build lock."""
    with log.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"command": list(map(str, command)), "cwd": str(cwd)}, ensure_ascii=False) + "\n")
        output.flush()
        child = subprocess.Popen(list(map(str, command)), cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess_flags())
        try:
            result = child.wait(timeout=timeout)
        except KeyboardInterrupt:
            # Keep the lock while the current writer settles. A second Ctrl+C
            # does not orphan it. Node/Pagefind can finish their own descendants.
            wait_owned_writer(child)
            raise
        except subprocess.TimeoutExpired:
            output.write(json.dumps({"timedOut": True, "action": "retain build lock and wait for the owned writer to exit"}) + "\n")
            output.flush()
            wait_owned_writer(child)
            raise RuntimeError("Owned preview step exceeded its time limit and has now exited; see " + str(log))
    if result:
        raise RuntimeError("Preview step failed (exit " + str(result) + "); see " + str(log))
    return {"command": list(map(str, command)), "exitCode": result, "log": str(log)}


def parse_export_log(path):
    rows = path.read_text(encoding="utf-8").splitlines()
    # The first line is our command record; stdout is one JSON document,
    # which may be pretty-printed. The parser rejects any trailing noise.
    if len(rows) < 2:
        raise ValueError("export-preview must produce one JSON result and no unrelated stdout")
    data = json.loads("\n".join(rows[1:]))
    if data.get("passed") is not True:
        raise ValueError("export-preview did not report success")
    return data


def decorate_html(document, title):
    if "data-kuhai-draft-preview" in document:
        raise ValueError("Preview HTML was already decorated")
    document = re.sub(r'<meta\b[^>]*\bname=["\']robots["\'][^>]*>', "", document, flags=re.I)
    metadata = '<meta name="robots" content="noindex,nofollow,noarchive">'
    document, count = re.subn(r"</head\s*>", metadata + "</head>", document, count=1, flags=re.I)
    if not count:
        # Astro redirect stubs legally omit the explicit head element.
        document, count = re.subn(r"(<!doctype\s+html\s*>)", lambda match: match.group(1) + metadata,
                                  document, count=1, flags=re.I)
        if not count:
            raise ValueError("Shirone HTML has neither a head nor an HTML doctype")
    notice = ('<aside data-kuhai-draft-preview data-pagefind-ignore role="note" '
              'style="margin:0 0 1rem;padding:.75rem 1rem;border-radius:12px;background:#172536;'
              'color:#f2f5fa;font:500 14px/1.6 system-ui,sans-serif;overflow-wrap:anywhere">'
              '本地草稿预览 · ' + html.escape(title) + '。此预览尚未发布，请勿上传此目录。</aside>')
    document, inserted = re.subn(r'(<main\b[^>]*\bid=["\']swup-container["\'][^>]*>)',
                                  lambda match: match.group(1) + notice, document, count=1, flags=re.I)
    if not inserted:
        document, inserted = re.subn(r'(<body\b[^>]*>)', lambda match: match.group(1) + notice,
                                      document, count=1, flags=re.I)
    if not inserted:
        raise ValueError("Shirone HTML has no body")
    return document


def finalize(snapshot, version, title, route):
    built = local(snapshot, "blog/dist")
    if not route.startswith("/blog/") or "?" in route or "#" in route or "%" in route:
        raise ValueError("Exported route must be an ordinary /blog/ local route")
    target_route = route.removeprefix("/blog/").strip("/")
    page = local(built, (target_route + "/" if target_route else "") + "index.html")
    if not page.is_file():
        raise ValueError("Built draft route is missing")
    for relative in safe_files(snapshot, "blog/dist"):
        path = local(snapshot, relative)
        if path.suffix.lower() == ".html":
            path.write_text(decorate_html(path.read_text(encoding="utf-8"), title), encoding="utf-8", newline="\n")
    (built / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    write_marker(built, version)
    output = snapshot / "dist"
    output.mkdir()
    write_marker(output, version)
    shutil.copytree(built, output / "blog")
    landing = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
               '<meta name="robots" content="noindex,nofollow,noarchive"><title>本地草稿预览</title></head>'
               '<body><main><h1>本地草稿预览</h1><p>内容尚未发布；此目录不能用于部署。</p><p><a href="' + html.escape(route, quote=True)
               + '">打开草稿：' + html.escape(title) + '</a></p><p><a href="/blog/">查看博客首页</a></p></main></body></html>')
    (output / "index.html").write_text(landing, encoding="utf-8")
    (output / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    return safe_files(snapshot, "dist")


def build(root, slug, version):
    safe_name(slug, "slug")
    safe_name(version, "version")
    folder = local(root, "preview-work", required=False)
    folder.mkdir(exist_ok=True)
    snapshot = local(root, "preview-work/" + version, required=False)
    if snapshot.exists():
        raise ValueError("Preview version already exists; choose a new version")
    record = {"schema": RECEIPT_SCHEMA, "previewOnly": True, "passed": False, "version": version,
              "slug": slug, "startedUTC": utc(), "steps": [], "notExecuted": ["browser acceptance", "production release", "deployment"]}
    with release_tools.exclusive_lock(root, "draft-" + version) as token:
        before = source_inventory(root, slug)
        runtime = resolve_runtime(root)
        environment = controlled_environment(runtime, root)
        environment["KUHAI_RELEASE_OWNER"] = token
        environment["CONTENT_DIR"] = str(snapshot / "content")
        snapshot.mkdir()
        write_marker(snapshot, version)
        logs = snapshot / "logs"
        logs.mkdir()
        try:
            copied = copy_inputs(root, snapshot)
            record["copiedSource"] = copied
            record["dependencyLinks"] = dependency_facade(root, snapshot)
            exporter = local(root, "blog/scripts/kuhai/writing.mjs")
            record["steps"].append(execute([runtime.node, exporter, "export-preview", slug, "--out", snapshot / "content"],
                                            root / "blog", environment, logs / "01-export.log"))
            exported = parse_export_log(logs / "01-export.log")
            if Path(exported.get("outputContent", "")) != snapshot / "content":
                raise ValueError("export-preview returned an unexpected output directory")
            record["export"] = exported
            record["steps"].append(execute([runtime.node, "scripts/kuhai/configure.mjs"], snapshot / "blog", environment, logs / "02-configure.log"))
            site = snapshot / "content/config/site.yaml"
            settings = json.loads(site.read_text(encoding="utf-8"))
            settings["site"] = DEFAULT_ORIGIN
            site.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            commands = [
                ("03-content-sync", [runtime.node, "scripts/content/sync.mjs"]),
                ("04-astro-build", [runtime.node, cli_entry(root, "astro", "astro"), "build"]),
                ("05-pagefind", [runtime.node, cli_entry(root, "pagefind", "pagefind"), "--site", "dist"]),
                ("06-font-check", [runtime.node, "scripts/fonts/check-fonts.mjs"]),
            ]
            for name, command in commands:
                record["steps"].append(execute(command, snapshot / "blog", environment, logs / (name + ".log")))
            record["outputs"] = finalize(snapshot, version, exported["title"], exported["route"])
            record["sourceUnchanged"] = before == source_inventory(root, slug)
            if not record["sourceUnchanged"]:
                raise RuntimeError("Author sources or ordinary blog output changed during the preview build")
            record.update({"passed": True, "route": exported["route"], "title": exported["title"], "runtime": runtime.as_dict(),
                           "canonicalSourceHashes": before, "finishedUTC": utc()})
        except BaseException as error:
            record.update({"error": str(error), "finishedUTC": utc()})
            atomic_json(snapshot / RECEIPT, record)
            raise
        atomic_json(snapshot / RECEIPT, record)
    return {"passed": True, "previewOnly": True, "version": version, "slug": slug, "route": record["route"],
            "receipt": str(snapshot / RECEIPT), "dist": str(snapshot / "dist")}


def ready_snapshot(root, version):
    safe_name(version, "version")
    snapshot = local(root, "preview-work/" + version)
    receipt = release_tools.load_json(local(snapshot, RECEIPT))
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("previewOnly") is not True or receipt.get("passed") is not True or receipt.get("version") != version:
        raise ValueError("Preview is not a completed private snapshot")
    for directory in (snapshot, local(snapshot, "dist"), local(snapshot, "dist/blog")):
        if release_tools.load_json(local(directory, MARKER)) != marker(version):
            raise ValueError("Preview marker is missing or changed")
    actual = safe_files(snapshot, "dist")
    if actual != receipt.get("outputs"):
        raise ValueError("Preview output changed after its successful build")
    return snapshot, receipt


def port_number(value):
    value = int(value)
    if not 1024 <= value <= 65535 or value in (4175, 4177):
        raise ValueError("Use a private loopback port 1024–65535 other than 4175/4177")
    return value


def load_server_helper(root):
    path = local(root, "scripts/serve-preview.py")
    spec = importlib.util.spec_from_file_location("kuhai_draft_static_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preview_handler(root, webroot, version, token, port):
    original = load_server_helper(root).make_handler(webroot)
    identity = {"schema": "kuhai-draft-preview-server-v1", "version": version, "pid": os.getpid(),
                "tokenHash": hashlib.sha256(token.encode()).hexdigest()}

    class Handler(original):
        def safe_path(self, request_target):
            target = super().safe_path(request_target)
            if target.name in (MARKER, RECEIPT):
                raise PermissionError("Private preview record is not served")
            return target

        def end_headers(self):
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            self.send_header("X-Kuhai-Draft-Preview", "true")
            super().end_headers()

        def memory_response(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)

        def send_head(self):
            if self.path == "/__draft_preview_health":
                return self.memory_response(json.dumps(identity).encode(), "application/json")
            try:
                target = self.safe_path(self.path)
                if target.is_dir() and urlsplit(self.path).path.endswith("/"):
                    target = self.safe_path(urlsplit(self.path).path + "index.html")
                if target.is_file() and target.suffix.lower() in (".html", ".xml", ".txt", ".json", ".js", ".mjs"):
                    # Config-generated absolute links follow the chosen local port.
                    body = target.read_text(encoding="utf-8").replace(DEFAULT_ORIGIN, "http://127.0.0.1:" + str(port)).encode("utf-8")
                    return self.memory_response(body, self.guess_type(str(target)))
            except (OSError, ValueError, UnicodeError):
                self.send_error(404)
                return None
            return super().send_head()

        def do_POST(self):
            if self.path != "/__draft_preview_stop" or not hmac.compare_digest(self.headers.get("X-Preview-Token", ""), token):
                self.send_error(404)
                return
            body = self.memory_response(b'{"stopping":true}', "application/json")
            self.wfile.write(body.read())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return Handler


@contextlib.contextmanager
def control_lock(root):
    folder = local(root, "preview-work", required=False)
    folder.mkdir(exist_ok=True)
    path = local(root, CONTROL_LOCK, required=False)
    token = uuid.uuid4().hex
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"token": token, "pid": os.getpid()}, stream)
    except FileExistsError as error:
        raise RuntimeError("Another preview start/stop operation owns the control lock") from error
    try:
        yield
    finally:
        if path.exists() and release_tools.load_json(path).get("token") == token:
            path.unlink()


def read_state(root):
    path = local(root, STATE, required=False)
    if not path.exists():
        return None
    data = release_tools.load_json(path)
    if data.get("schema") != "kuhai-draft-preview-process-v1" or not re.fullmatch(r"[a-f0-9]{32}", str(data.get("token", ""))):
        raise ValueError("Invalid private preview process record")
    safe_name(data.get("version"), "version")
    port_number(data.get("port"))
    if type(data.get("pid")) is not int or data["pid"] < 1:
        raise ValueError("Invalid private preview process identity")
    return data


def health(state):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{state["port"]}/__draft_preview_health', timeout=2) as response:
            data = json.loads(response.read(4096))
        return data == {"schema": "kuhai-draft-preview-server-v1", "version": state["version"], "pid": state["pid"],
                        "tokenHash": hashlib.sha256(state["token"].encode()).hexdigest()}
    except (OSError, ValueError):
        return False


def status(root):
    record = read_state(root)
    if record is None:
        return {"status": "NOT_STARTED", "previewOnly": True}
    return {"status": "RUNNING" if record.get("status") == "RUNNING" and health(record) else record.get("status") if record.get("status") != "RUNNING" else "UNREACHABLE",
            "previewOnly": True, "version": record["version"], "pid": record["pid"],
            "url": f'http://127.0.0.1:{record["port"]}/' + record.get("route", "").lstrip("/")}


def serve(root, version, port):
    port = port_number(port)
    snapshot, receipt = ready_snapshot(root, version)
    lock = local(root, SERVER_LOCK, required=False)
    token = uuid.uuid4().hex
    record = {"schema": "kuhai-draft-preview-process-v1", "previewOnly": True, "version": version, "port": port,
              "pid": os.getpid(), "token": token, "status": "STARTING", "route": receipt["route"], "startedUTC": utc()}
    with lock.open("x", encoding="utf-8") as stream:
        json.dump(record, stream)
    try:
        with ThreadingHTTPServer(("127.0.0.1", port), preview_handler(root, snapshot / "dist", version, token, port)) as server:
            server.daemon_threads = True
            record["status"] = "RUNNING"
            atomic_json(local(root, STATE, required=False), record)
            print(json.dumps({"status": "RUNNING", "previewOnly": True, "url": f"http://127.0.0.1:{port}" + receipt["route"]}), flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
    finally:
        record.update({"status": "STOPPED", "stoppedUTC": utc()})
        state = read_state(root)
        if state and state["token"] == token:
            atomic_json(local(root, STATE), record)
        if lock.exists() and release_tools.load_json(lock).get("token") == token:
            lock.unlink()


def start(root, version, port):
    port = port_number(port)
    snapshot, _ = ready_snapshot(root, version)
    with control_lock(root):
        if local(root, SERVER_LOCK, required=False).exists():
            raise RuntimeError("A preview server lock exists; inspect preview-status and stop the owned preview first")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        log = snapshot / ("server-" + uuid.uuid4().hex + ".log")
        with log.open("xb") as output:
            child = subprocess.Popen([sys.executable, "-B", str(local(root, "scripts/draft_preview.py")), "serve", version, "--port", str(port)],
                                     cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess_flags())
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                record = read_state(root)
                if record and record["pid"] == child.pid and record.get("status") == "RUNNING" and health(record):
                    return {**status(root), "log": str(log)}
                if child.poll() is not None:
                    raise RuntimeError("Owned preview server did not start; see " + str(log))
                time.sleep(0.15)
            raise RuntimeError("Owned preview server startup timed out; see " + str(log))
        except BaseException:
            # This Popen still owns the exact newly created child handle.
            # Never stop a PID looked up from an old or malformed state file.
            if child.poll() is None:
                child.terminate()
                wait_owned_writer(child)
            raise


def stop(root):
    with control_lock(root):
        record = read_state(root)
        if record is None or record.get("status") != "RUNNING":
            return status(root)
        if not health(record):
            raise RuntimeError("Cannot verify the recorded preview server; no process was stopped and the record was retained")
        request = urllib.request.Request(f'http://127.0.0.1:{record["port"]}/__draft_preview_stop', data=b"",
                                         headers={"X-Preview-Token": record["token"]}, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            response.read(4096)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = read_state(root)
            if current and current["token"] == record["token"] and current["status"] == "STOPPED" and not local(root, SERVER_LOCK, required=False).exists():
                return status(root)
            time.sleep(0.15)
        raise RuntimeError("Owned preview shutdown has not been confirmed; state retained")


def dispatch(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    build_args = commands.add_parser("build")
    build_args.add_argument("slug")
    build_args.add_argument("--version", required=True)
    for name in ("start", "serve"):
        command = commands.add_parser(name)
        command.add_argument("version")
        command.add_argument("--port", type=int, default=4180)
    commands.add_parser("stop")
    commands.add_parser("status")
    args = parser.parse_args(argv)
    if args.mode == "build":
        return build(ROOT, args.slug, args.version)
    if args.mode == "start":
        return start(ROOT, args.version, args.port)
    if args.mode == "serve":
        serve(ROOT, args.version, args.port)
        return {"status": "STOPPED", "previewOnly": True}
    return stop(ROOT) if args.mode == "stop" else status(ROOT)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(dispatch(argv), ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"passed": False, "previewOnly": True, "error": "Preview operation interrupted; owned writer has finished."}, ensure_ascii=False), file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"passed": False, "previewOnly": True, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
