"""Serve a built release on loopback (default port 4177). No browser is opened."""
import argparse
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

RELEASE = Path(__file__).resolve().parents[1]
PRIVATE_SUFFIX = re.compile(r"\.(?:map|ts|tsx|jsx|astro|vue|svelte|md|mdx|py|pyc|sh|ps1|bat|cmd|blend[0-9]*|pem|key|env|ini|toml|ya?ml|lock|bak|log|sql)(?:\.(?:gz|br))?$", re.I)
PRIVATE_NAMES = re.compile(r"(?:site\.json|package(?:-lock)?\.json|tsconfig(?:\.[^/]+)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Dockerfile|Makefile)(?:\.(?:gz|br))?$", re.I)
PRIVATE_DIRS = {"src", "node_modules", "deployment", "evidence", "scripts", "content", "runtime"}


def redirected(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def make_handler(root):
    class PreviewHandler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        extensions_map = {
            **SimpleHTTPRequestHandler.extensions_map,
            ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
            ".json": "application/json", ".jsonld": "application/ld+json",
            ".xml": "application/xml", ".txt": "text/plain; charset=utf-8",
            ".webmanifest": "application/manifest+json", ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json", ".wasm": "application/wasm", ".bin": "application/octet-stream",
            ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
            ".svg": "image/svg+xml", ".pagefind": "application/octet-stream",
            ".pf_fragment": "application/octet-stream", ".pf_index": "application/octet-stream", ".pf_meta": "application/octet-stream",
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def safe_path(self, request_target):
            parsed = urlsplit(request_target)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
                raise PermissionError("Only origin-form local paths are served")
            path = unquote(parsed.path, errors="strict")
            if any(ord(char) < 32 or char in "\\:" for char in path):
                raise PermissionError("Unsafe path characters")
            parts = tuple(part for part in path.split("/") if part)
            if any(part.endswith((".", " ")) or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, flags=re.I) for part in parts):
                raise PermissionError("Ambiguous or reserved filesystem name")
            if any(part in {".", ".."} or (part.startswith(".") and not (index == 0 and part == ".well-known")) for index, part in enumerate(parts)):
                raise PermissionError("Hidden or traversing path")
            visible_parts = parts[1:] if parts and parts[0] == "blog" else parts
            if visible_parts and visible_parts[0].lower() in PRIVATE_DIRS:
                raise PermissionError("Source directory is not public")
            if parts and (PRIVATE_SUFFIX.search(parts[-1]) or PRIVATE_NAMES.fullmatch(parts[-1])):
                raise PermissionError("Source/config file is not public")
            target = root
            if redirected(root) or root.resolve() != root:
                raise PermissionError("Preview root changed")
            for part in parts:
                target = target / part
                if redirected(target):
                    raise PermissionError("Linked files are not served")
            if not target.resolve().is_relative_to(root):
                raise PermissionError("Path escapes preview root")
            return target

        def translate_path(self, path):
            return str(self.safe_path(path))

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            super().end_headers()

        def send_head(self):
            try:
                target = self.safe_path(self.path)
                parsed = urlsplit(self.path)
                if parsed.path in {"/404.html", "/blog/404.html"}:
                    self.send_error(404)
                    return None
                if target.is_dir():
                    index = target / "index.html"
                    if redirected(index) or not index.is_file():
                        self.send_error(404)
                        return None
                    if not parsed.path.endswith("/"):
                        location = urlunsplit(("", "", quote(unquote(parsed.path, errors="strict").rstrip("/") + "/", safe="/"), parsed.query, ""))
                        self.send_response(308)
                        self.send_header("Location", location)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return None
                return super().send_head()
            except (OSError, ValueError, UnicodeError):
                self.send_error(404)
                return None

        def list_directory(self, path):
            self.send_error(404)
            return None

        def send_error(self, code, message=None, explain=None):
            if code != 404:
                return super().send_error(code, message, explain)
            try:
                error_file = self.safe_path("/404.html")
                if not error_file.is_file() or error_file.stat().st_size > 8 * 1024 * 1024:
                    raise OSError("Custom error page unavailable")
                body = error_file.read_bytes()
            except (OSError, ValueError, UnicodeError):
                body = b"<!doctype html><html lang=en><meta charset=utf-8><title>404</title><h1>404</h1><p>Page not found.</p></html>"
            self.send_response(404, "Not Found")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return None

    return PreviewHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", nargs="?", default="dist", help="Assembled dist or dist-NAME under this release")
    parser.add_argument("--port", type=int, default=4177, help="Local comparison port; the existing preview is never stopped")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Use a loopback port between 1024 and 65535")
    supplied = Path(args.dist)
    root = supplied if supplied.is_absolute() else RELEASE / supplied
    if root.parent != RELEASE or not re.fullmatch(r"dist(?:-[A-Za-z0-9_-]+)?", root.name):
        raise ValueError("Serve only a direct dist or dist-NAME child of the release")
    if redirected(root) or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("Preview requires a real assembled directory")
    for entry in ("index.html", "blog/index.html", "404.html"):
        if not (root / entry).is_file() or redirected(root / entry):
            raise ValueError(f"Incomplete release: {entry}")
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(root)) as server:
        print(json.dumps({"url": f"http://127.0.0.1:{args.port}/", "root": str(root), "cache": "no-store", "scope": "local preview, not production Nginx or browser acceptance"}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Preview not started: {error}")
