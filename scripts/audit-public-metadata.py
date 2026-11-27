"""Read-only audit of local paths in one existing release dist-* or ship/public-*.

JSON string values and PNG File text metadata are inspected for local absolute
paths. All other files are searched only for exact known workspace-root bytes.
The JSON report contains hashes and issue keys, never full metadata values.
No assets, reports, network settings or processes are modified by this script.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import struct
import sys
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RELEASE = Path(__file__).resolve().parents[1]
JSON_LIMIT = 16 * 1024 * 1024
PNG_LIMIT = 64 * 1024 * 1024
PNG_TEXT_LIMIT = 8 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LOCAL_PATH = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+|file://)|"
    r"(?<![a-zA-Z0-9:/])/(?:Users|home|root|private|tmp|mnt|media|srv|var)/"
)
# Fixed, known local workspace roots only. No credential/config discovery.
KNOWN_ROOT_TEXT = (
    "D:/Code/personal_website",
    "D:\\Code\\personal_website",
    "D:\\\\Code\\\\personal_website",
)
KNOWN_ROOT_BYTES = tuple(dict.fromkeys(text.encode(encoding) for text in KNOWN_ROOT_TEXT for encoding in ("utf-8", "utf-16-le", "utf-16-be")))


def redirected(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def public_root(value):
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else RELEASE / supplied
    if ".." in candidate.parts or not candidate.is_relative_to(RELEASE):
        raise ValueError("Root must remain directly under this release")
    allowed = (
        candidate.parent == RELEASE and re.fullmatch(r"dist-[A-Za-z0-9][A-Za-z0-9_-]*", candidate.name)
    ) or (
        candidate.parent == RELEASE / "ship" and re.fullmatch(r"public-[A-Za-z0-9][A-Za-z0-9_-]*", candidate.name)
    )
    if not allowed:
        raise ValueError("Accepts only existing dist-NAME or ship/public-NAME directories")
    cursor = RELEASE
    for part in candidate.relative_to(RELEASE).parts:
        cursor /= part
        if redirected(cursor):
            raise ValueError("Linked root or ancestor is forbidden")
    if not candidate.is_dir() or candidate.resolve(strict=True) != candidate:
        raise ValueError("Root must be an existing real directory without aliases")
    return candidate


def issue(kind, key):
    return {"kind": kind, "key": key}


def json_path_issues(value, key=""):
    found = []
    if isinstance(value, dict):
        for name, item in value.items():
            pointer = str(name).replace("~", "~0").replace("/", "~1")
            found.extend(json_path_issues(item, key + "/" + pointer))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(json_path_issues(item, key + "/" + str(index)))
    elif isinstance(value, str) and LOCAL_PATH.search(value):
        found.append(issue("local_absolute_path", key or "/"))
    return found


def bounded_decompress(data):
    decoder = zlib.decompressobj()
    result = decoder.decompress(data, PNG_TEXT_LIMIT + 1)
    if len(result) > PNG_TEXT_LIMIT or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise ValueError("Invalid or excessive compressed PNG text")
    return result


def png_file_metadata_issues(data):
    if not data.startswith(PNG_SIGNATURE):
        return [issue("invalid_png_signature", "/")]
    position = 8
    ended = False
    found = []
    counts = Counter()
    while position + 12 <= len(data):
        length = struct.unpack_from(">I", data, position)[0]
        tag = data[position + 4:position + 8]
        end = position + 12 + length
        if end > len(data):
            return found + [issue("truncated_png_chunk", "/")]
        payload = data[position + 8:position + 8 + length]
        stored_crc = struct.unpack_from(">I", data, position + 8 + length)[0]
        if zlib.crc32(payload, zlib.crc32(tag)) & 0xffffffff != stored_crc:
            return found + [issue("invalid_png_chunk_crc", "/")]
        position = end
        if tag in (b"tEXt", b"zTXt", b"iTXt"):
            label = tag.decode("ascii")
            counts[label] += 1
            keyword, separator, rest = payload.partition(b"\0")
            key = f"/{label}/{counts[label]}/File"
            if not separator:
                found.append(issue("malformed_png_text", f"/{label}/{counts[label]}"))
                continue
            if keyword.lower() != b"file":
                continue
            try:
                if tag == b"tEXt":
                    if len(rest) > PNG_TEXT_LIMIT:
                        raise ValueError("Excessive PNG text")
                    text = rest.decode("latin-1")
                elif tag == b"zTXt":
                    if not rest or rest[0] != 0:
                        raise ValueError("Invalid PNG compression method")
                    text = bounded_decompress(rest[1:]).decode("latin-1")
                else:
                    if len(rest) < 2 or rest[0] not in (0, 1) or rest[1] != 0:
                        raise ValueError("Invalid international PNG text header")
                    fields = rest[2:].split(b"\0", 2)
                    if len(fields) != 3:
                        raise ValueError("Invalid international PNG text fields")
                    text_bytes = bounded_decompress(fields[2]) if rest[0] else fields[2]
                    if len(text_bytes) > PNG_TEXT_LIMIT:
                        raise ValueError("Excessive international PNG text")
                    text = text_bytes.decode("utf-8")
                if LOCAL_PATH.search(text):
                    found.append(issue("png_file_local_absolute_path", key))
            except (ValueError, UnicodeError, zlib.error):
                found.append(issue("invalid_or_excessive_png_file_metadata", key))
        if tag == b"IEND":
            ended = True
            break
    if not ended:
        found.append(issue("missing_png_iend", "/"))
    elif position != len(data):
        found.append(issue("trailing_png_bytes_not_inspected", "/"))
    return found


def scan_file(path, relative):
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        return {"path": relative, "bytes": None, "sha256": None, "issues": [issue("not_regular_file", "/")]}
    suffix = path.suffix.lower()
    format_name = "json" if suffix == ".json" else ("png" if suffix == ".png" else "exact_known_root_bytes_only")
    limit = JSON_LIMIT if format_name == "json" else (PNG_LIMIT if format_name == "png" else 0)
    chunks = []
    digest = hashlib.sha256()
    size = 0
    matched_known = False
    tail = b""
    overlap = max(map(len, KNOWN_ROOT_BYTES)) - 1
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
            if format_name == "exact_known_root_bytes_only":
                probe = tail + block
                matched_known |= any(pattern in probe for pattern in KNOWN_ROOT_BYTES)
                tail = probe[-overlap:]
            elif before.st_size <= limit and size <= limit:
                chunks.append(block)
    after = path.stat(follow_symlinks=False)
    found = []
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or size != before.st_size:
        found.append(issue("file_changed_during_scan", "/"))
    if format_name != "exact_known_root_bytes_only" and (before.st_size > limit or size > limit):
        found.append(issue("structured_metadata_exceeds_scan_limit", "/"))
    elif format_name == "json":
        try:
            found.extend(json_path_issues(json.loads(b"".join(chunks).decode("utf-8-sig"))))
        except (ValueError, UnicodeError, RecursionError):
            found.append(issue("invalid_json_metadata", "/"))
    elif format_name == "png":
        found.extend(png_file_metadata_issues(b"".join(chunks)))
    elif matched_known:
        found.append(issue("exact_known_workspace_root_bytes", "/$bytes"))
    return {"path": relative, "bytes": size, "sha256": digest.hexdigest(), "format": format_name, "issues": found}


def scan_tree(root):
    files = []
    tree_issues = []
    def walk_error(error):
        tree_issues.append(issue("directory_unreadable", Path(error.filename).relative_to(root).as_posix()))
    for directory, subdirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        subdirs.sort()
        for name in subdirs[:]:
            candidate = Path(directory) / name
            if redirected(candidate):
                tree_issues.append(issue("linked_directory_forbidden", candidate.relative_to(root).as_posix()))
                subdirs.remove(name)
        for name in sorted(names):
            candidate = Path(directory) / name
            relative = candidate.relative_to(root).as_posix()
            if redirected(candidate):
                tree_issues.append(issue("linked_file_forbidden", relative))
                continue
            try:
                if candidate.resolve(strict=True) != candidate or not candidate.is_relative_to(root):
                    tree_issues.append(issue("file_alias_or_escape_forbidden", relative))
                    continue
                files.append(scan_file(candidate, relative))
            except OSError:
                tree_issues.append(issue("file_unreadable", relative))
    counts = Counter(item.get("format", "unreadable") for item in files)
    issues_count = len(tree_issues) + sum(len(item["issues"]) for item in files)
    return {
        "schema": "kuhai-public-metadata-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "root": root.relative_to(RELEASE).as_posix(), "passed": issues_count == 0,
        "scanned_files": len(files), "scanned_bytes": sum(item["bytes"] or 0 for item in files),
        "format_counts": dict(counts), "files_with_issues": sum(bool(item["issues"]) for item in files),
        "issues_count": issues_count, "tree_issues": tree_issues,
        "files": sorted(files, key=lambda item: item["path"]),
        "scope": "JSON string local paths; PNG tEXt/zTXt/iTXt File fields; other files exact known workspace-root byte patterns only. No values or full metadata are copied to this report.",
        "not_executed": ["asset_modification", "outside_tree_read", "network", "installation", "browser", "server", "release_acceptance"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Existing dist-NAME or ship/public-NAME under this release")
    args = parser.parse_args()
    try:
        result = scan_tree(public_root(args.root))
    except (OSError, ValueError) as error:
        # Do not echo input filesystem paths from operating-system errors.
        print(json.dumps({"schema": "kuhai-public-metadata-audit-v1", "passed": False, "status": "rejected_root", "error_type": type(error).__name__}, separators=(",", ":")))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
