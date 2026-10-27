"""Assemble two finished static builds into a NEW release directory; no deployment."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.sax.saxutils import escape

RELEASE = Path(__file__).resolve().parents[1]
ORIGIN = "https://kuhaiyongcun.com"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
STATIC_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".jsonld", ".xml",
    ".rss", ".atom", ".txt", ".webmanifest", ".wasm", ".glb", ".gltf", ".bin",
    ".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf", ".mp4", ".webm",
    ".mp3", ".ogg", ".wav", ".pagefind", ".pf_fragment", ".pf_index", ".pf_meta",
}
PRIVATE_NAMES = re.compile(r"(?:site\.json|package(?:-lock)?\.json|tsconfig(?:\.[^/]+)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Dockerfile|Makefile)(?:\.(?:gz|br))?$", re.I)
PRIVATE_DIRS = {"src", "node_modules", "deployment", "evidence", "scripts", "content", "runtime"}
ROOT_GENERATED = {"404.html", "robots.txt", "sitemap.xml", "sitemap-index.xml"}
DISABLED_MODULES = {"albums", "anime", "compass", "devices", "friends", "games", "moments", "projects", "series", "skills", "timeline"}
PRIVATE_AUTHORING_ROOTS = {"authoring-private", "preview-work"}
PREVIEW_SENTINELS = ("PREVIEW-ONLY.json", "draft-preview-receipt.json")
CSS_URL = re.compile(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)]+))\s*\)", re.I)


def is_redirected(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path, maximum=8 * 1024 * 1024):
    if path.stat().st_size > maximum:
        raise ValueError(f"Text resource too large to inspect: {path}")
    return path.read_text(encoding="utf-8-sig")


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
        if is_redirected(current):
            raise ValueError("Linked publication input is forbidden: " + relative.as_posix())
    current = path if path.is_dir() else path.parent
    while True:
        for filename in PREVIEW_SENTINELS:
            marker = current / filename
            # Presence is enough: malformed or linked preview receipts must
            # never become ordinary publishable JSON assets.
            if marker.exists() or is_redirected(marker):
                raise ValueError("Preview-only marker/receipt prohibits publication: " + marker.relative_to(RELEASE).as_posix())
        if current == RELEASE:
            break
        current = current.parent


def source_root(value, component):
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = RELEASE / candidate
    reject_preview_input(candidate)
    expected_parent = RELEASE / component
    if candidate.parent != expected_parent or not re.fullmatch(r"dist(?:-[A-Za-z0-9_-]+)?", candidate.name):
        raise ValueError(f"{component} input must be its dist or dist-NAME directory")
    if is_redirected(candidate) or candidate.resolve(strict=True) != candidate or not candidate.is_dir():
        raise ValueError(f"Input must be a real directory: {candidate}")
    entry = candidate / "index.html"
    if not entry.is_file() or is_redirected(entry):
        raise ValueError(f"Missing regular input index.html: {candidate}")
    return candidate


def excluded_reason(relative, is_directory=False):
    parts = relative.parts
    if any(part.startswith(".") and not (index == 0 and part == ".well-known") for index, part in enumerate(parts)):
        return "hidden_path"
    if parts[0].lower() in PRIVATE_DIRS:
        return "source_or_delivery_directory"
    if PRIVATE_NAMES.fullmatch(parts[-1]):
        return "private_or_build_config"
    if not is_directory and relative.suffix.lower() not in STATIC_EXTENSIONS:
        if len(parts) == 3 and parts[:2] == (".well-known", "acme-challenge") and re.fullmatch(r"[A-Za-z0-9_-]+", parts[-1]):
            return None
        return "not_an_allowed_static_file_type"
    return None


def disabled_stub_evidence(directory):
    members = list(directory.iterdir())
    if len(members) != 1 or members[0].name != "index.html" or is_redirected(members[0]) or not members[0].is_file():
        raise ValueError(f"Disabled module is not a single known redirect stub: {directory}")
    text = read_text(members[0], 2048)

    class RedirectProbe(HTMLParser):
        refresh = None

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "meta" and values.get("http-equiv", "").lower() == "refresh":
                self.refresh = values.get("content", "")

    probe = RedirectProbe()
    probe.feed(text)
    if not probe.refresh or not re.fullmatch(r"\s*\d+(?:\.\d+)?\s*;\s*url=/blog/404(?:/|\.html)\s*", probe.refresh, flags=re.I) or "Redirecting" not in text:
        raise ValueError(f"Refusing to discard unrecognized disabled-module content: {directory}")
    return {"stub_path": "index.html", "bytes": members[0].stat().st_size, "sha256": sha256(members[0]), "refresh": probe.refresh}


def collect(source, component, exclusions):
    selected = []
    for directory, subdirs, filenames in os.walk(source, followlinks=False):
        reject_preview_input(Path(directory))
        subdirs.sort()
        for name in subdirs[:]:
            path = Path(directory) / name
            relative = path.relative_to(source)
            reason = "symlink_or_junction" if is_redirected(path) else excluded_reason(relative, True)
            if component == "blog" and len(relative.parts) == 1 and name in DISABLED_MODULES and not reason:
                exclusions.append({"component": component, "path": relative.as_posix(), "reason": "explicitly_disabled_module_refresh_stub", **disabled_stub_evidence(path)})
                subdirs.remove(name)
                continue
            if component == "ship" and relative.parts[0] == "blog":
                raise ValueError("Ship build already contains reserved /blog/ namespace")
            if reason:
                exclusions.append({"component": component, "path": relative.as_posix(), "reason": reason})
                subdirs.remove(name)
        for name in sorted(filenames):
            path = Path(directory) / name
            relative = path.relative_to(source)
            reason = "symlink_or_junction" if is_redirected(path) else excluded_reason(relative)
            if component == "ship" and relative.as_posix() in ROOT_GENERATED:
                reason = "root_metadata_generated_by_assembler"
            if reason:
                exclusions.append({"component": component, "path": relative.as_posix(), "reason": reason})
                continue
            if not path.is_file():
                raise ValueError(f"Not a regular input file: {path}")
            selected.append((path, relative))
    return selected


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    digest = hashlib.sha256()
    count = 0
    with source.open("rb") as reader, target.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
            count += len(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or count != before.st_size:
        raise ValueError(f"Input changed during copy: {source}")
    return {"bytes": count, "sha256": digest.hexdigest()}


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.styles = []
        self.in_style = False
        self.has_body = False
        self.meta_refresh = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.has_body |= tag == "body"
        self.meta_refresh |= tag == "meta" and values.get("http-equiv", "").lower() == "refresh"
        if tag == "base":
            raise ValueError("A base element requires explicit manual asset review")
        if tag == "style":
            self.in_style = True
        if values.get("style"):
            self.styles.append(values["style"])
        for key in (("src", "poster") if tag in {"script", "img", "source", "video", "audio", "iframe", "input"} else ()):
            if values.get(key):
                self.references.append(values[key])
        if tag == "link" and set(values.get("rel", "").lower().split()) & {"stylesheet", "icon", "preload", "modulepreload", "apple-touch-icon", "manifest"}:
            if values.get("href"):
                self.references.append(values["href"])
        if values.get("srcset") and not values["srcset"].lstrip().startswith("data:"):
            self.references.extend(part.strip().split()[0] for part in values["srcset"].split(",") if part.strip())

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)


def local_asset(root, ref, source_url, external):
    ref = ref.strip()
    if not ref or ref.startswith(("#", "data:", "blob:")):
        return
    parsed = urlsplit(urljoin(source_url, ref))
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unexpected asset scheme: {ref}")
    if (parsed.scheme, parsed.netloc) != ("https", "kuhaiyongcun.com"):
        external.add(parsed.geturl())
        return
    decoded = unquote(parsed.path, errors="strict")
    if "\\" in decoded or ":" in decoded or ".." in decoded.split("/"):
        raise ValueError(f"Unsafe local asset URL: {ref}")
    target = root.joinpath(*decoded.lstrip("/").split("/"))
    if not target.is_file() or not target.resolve().is_relative_to(root) or is_redirected(target):
        raise ValueError(f"Missing local asset: {ref} from {source_url}")


def verify_assets(root):
    checked = 0
    external = set()
    for path in sorted(root.rglob("*.html")):
        relative = path.relative_to(root).as_posix()
        parser = AssetReferences()
        text = read_text(path)
        parser.feed(text)
        if relative in {"404.html", "blog/404.html"}:
            if parser.meta_refresh or not parser.has_body or len(text) < 1024:
                raise ValueError(f"404 must be a complete HTML page, not a refresh stub: {relative}")
        route = "/" + relative
        if route.endswith("/index.html"):
            route = route[:-len("index.html")]
        for ref in parser.references + [next(value for value in match.groups() if value is not None) for style in parser.styles for match in CSS_URL.finditer(style)]:
            if relative == "404.html" and ref and not ref.startswith(("/", "#", "data:", "blob:", "https://", "http://")):
                raise ValueError(f"Root error-page resource must have an absolute URL: {ref}")
            local_asset(root, ref, ORIGIN + route, external)
            checked += 1
    for path in sorted(root.rglob("*.css")):
        source_url = ORIGIN + "/" + path.relative_to(root).as_posix()
        for match in CSS_URL.finditer(read_text(path)):
            local_asset(root, next(value for value in match.groups() if value is not None), source_url, external)
            checked += 1
    return {"html_and_css_asset_references_checked": checked, "external_assets_not_fetched": sorted(external), "limits": "Does not execute JavaScript, load GLB, or replace browser acceptance."}


def verify_blog_sitemaps(root):
    pending = [root / "blog/sitemap-index.xml"]
    visited = set()
    page_count = 0
    leaves = []
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        if len(visited) >= 64:
            raise ValueError("Unexpectedly many sitemap files")
        visited.add(path)
        document = ET.fromstring(read_text(path, 2 * 1024 * 1024))
        kind = document.tag.rsplit("}", 1)[-1]
        if kind not in {"sitemapindex", "urlset"} or document.tag != f"{{{SITEMAP_NS}}}{kind}" or not len(document):
            raise ValueError(f"Invalid sitemap root: {path}")
        if kind == "sitemapindex" and path != root / "blog/sitemap-index.xml":
            raise ValueError("Nested blog sitemap indexes are not supported")
        if kind == "urlset":
            leaves.append(ORIGIN + "/" + path.relative_to(root).as_posix())
        for entry in document:
            location = entry.find(f"{{{SITEMAP_NS}}}loc")
            parsed = urlsplit(location.text if location is not None and location.text else "")
            if (parsed.scheme, parsed.netloc) != ("https", "kuhaiyongcun.com") or not parsed.path.startswith("/blog/") or parsed.query or parsed.fragment:
                raise ValueError(f"Sitemap URL is not a canonical /blog/ URL: {location.text if location is not None else None}")
            decoded = unquote(parsed.path, errors="strict")
            if ".." in decoded.split("/") or "\\" in decoded or ":" in decoded:
                raise ValueError("Unsafe sitemap path")
            target = root / decoded.lstrip("/")
            if kind == "sitemapindex":
                if not target.is_file() or target.suffix != ".xml":
                    raise ValueError(f"Missing referenced sitemap: {target}")
                pending.append(target)
            else:
                if not target.is_file() and not (target / "index.html").is_file():
                    raise ValueError(f"Sitemap page does not exist: {target}")
                page_count += 1
    return {"sitemap_files": len(visited), "page_urls": page_count, "leaf_sitemaps": sorted(leaves), "source_index": ORIGIN + "/blog/sitemap-index.xml"}


def write_new_text(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ship-dist", default="ship/dist")
    parser.add_argument("--blog-dist", default="blog/dist")
    parser.add_argument("--out", default="dist", help="New direct child, e.g. dist-v2; never overwritten")
    args = parser.parse_args()
    if not re.fullmatch(r"dist(?:-[A-Za-z0-9_-]+)?", args.out):
        raise ValueError("Output must be named dist or dist-NAME")
    output = RELEASE / args.out
    if output.exists() or is_redirected(output):
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")
    config = json.loads(read_text(RELEASE / "site.json", 64 * 1024))
    if config["site"]["url"].rstrip("/") != ORIGIN or config["site"]["blogBase"] != "/blog/":
        raise ValueError("Shared public origin/base does not match this release contract")
    ship = source_root(args.ship_dist, "ship")
    blog = source_root(args.blog_dist, "blog")
    for required in ("404.html", "sitemap-index.xml"):
        if not (blog / required).is_file() or is_redirected(blog / required):
            raise ValueError(f"Blog build is incomplete: {required}")
    exclusions = []
    inputs = {"ship": collect(ship, "ship", exclusions), "blog": collect(blog, "blog", exclusions)}
    evidence = RELEASE / "evidence"
    if is_redirected(evidence) or evidence.resolve() != evidence:
        raise ValueError("Evidence directory must remain inside this release")
    evidence.mkdir(exist_ok=True)
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    stem = f"assembly-{args.out}-{token}"
    report_path = evidence / f"{stem}.json"
    preflight_path = evidence / f"{stem}-preflight.json"
    report = {"schema": "kuhai-static-assembly-v1", "created_at": datetime.now(timezone.utc).isoformat(), "output": args.out, "origin": ORIGIN, "blog_base": "/blog/", "passed": False, "source_builds": {"ship": str(ship), "blog": str(blog)}, "excluded_source_entries": exclusions, "copied": [], "generated": [], "not_executed": ["deploy", "nginx_-t", "browser", "filing_approval"]}
    output.mkdir()
    try:
        for component, selected in inputs.items():
            for source, relative in selected:
                destination = output / relative if component == "ship" else output / "blog" / relative
                if destination == output / "blog":
                    raise ValueError("Ship build collides with the reserved /blog/ namespace")
                row = copy_file(source, destination)
                report["copied"].append({"component": component, "source_path": relative.as_posix(), "path": destination.relative_to(output).as_posix(), **row})
        copy_file(output / "blog/404.html", output / "404.html")
        report["blog_sitemap_check"] = verify_blog_sitemaps(output)
        root_index_entries = "".join(f"<sitemap><loc>{escape(url)}</loc></sitemap>" for url in [ORIGIN + "/sitemap.xml", *report["blog_sitemap_check"]["leaf_sitemaps"]])
        generated = {
            "robots.txt": f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap-index.xml\nSitemap: {ORIGIN}/blog/sitemap-index.xml\n",
            "sitemap.xml": f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="{SITEMAP_NS}"><url><loc>{ORIGIN}/</loc></url></urlset>\n',
            "sitemap-index.xml": f'<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="{SITEMAP_NS}">{root_index_entries}</sitemapindex>\n',
        }
        for filename, content in generated.items():
            write_new_text(output / filename, content)
        report["generated"] = [{"path": name, "bytes": (output / name).stat().st_size, "sha256": sha256(output / name)} for name in ("404.html", *generated)]
        report["root_404_matches_blog_404"] = sha256(output / "404.html") == sha256(output / "blog/404.html")
        checker = RELEASE / "deployment/preflight.py"
        run = subprocess.run([sys.executable, "-B", str(checker), str(output)], capture_output=True, text=True, encoding="utf-8", cwd=RELEASE, timeout=180)
        write_new_text(preflight_path, run.stdout)
        report["preflight"] = {"path": preflight_path.relative_to(RELEASE).as_posix(), "exit_code": run.returncode, "sha256": sha256(preflight_path), "checker_sha256": sha256(checker), "stderr": run.stderr}
        if run.returncode != 0:
            raise ValueError("Release preflight failed; output and evidence are retained")
        checked = json.loads(run.stdout)
        if checked.get("passed") is not True:
            raise ValueError("Preflight did not affirm success")
        report["files"] = checked["files"]
        report["files_count"] = checked["files_count"]
        report["total_bytes"] = checked["total_bytes"]
        report["asset_check"] = verify_assets(output)
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["assembler_sha256"] = sha256(Path(__file__))
        write_new_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(output), "evidence": str(report_path), "evidence_sha256": sha256(report_path), "error": report.get("error"), "files_count": report.get("files_count"), "total_bytes": report.get("total_bytes")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Assembly stopped before completion: {error}", file=sys.stderr)
        raise SystemExit(1)
