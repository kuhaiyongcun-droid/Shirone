"""Resolve installed tools without downloads, personal paths, or account configs."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PNPM_NO_AUTO_INSTALL_ARGS = ("--config.verify-deps-before-run=false",)


class RuntimeResolutionError(RuntimeError):
    pass


@dataclass
class RuntimePaths:
    node: Path
    pnpm: Path
    python: Path
    versions: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return {"node": str(self.node), "pnpm": str(self.pnpm), "python": str(self.python),
                "versions": self.versions, "sources": self.sources, "warnings": self.warnings}


def subprocess_flags():
    """CREATE_NO_WINDOW is meaningful only on Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _file(value, root, label):
    if not isinstance(value, str) or not value.strip():
        raise RuntimeResolutionError(label + " must identify an installed file")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise RuntimeResolutionError(label + " does not exist: " + str(candidate))
    return candidate


def _local_config(root):
    explicit = os.environ.get("KUHAI_TOOLCHAIN_CONFIG")
    path = _file(explicit, root, "KUHAI_TOOLCHAIN_CONFIG") if explicit else root / "toolchain-local.json"
    if not path.is_file():
        return {}, None
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise RuntimeResolutionError("Cannot read the explicit local toolchain config: " + str(path)) from exc
    if not isinstance(config, dict) or set(config) - {"schemaVersion", "node", "pnpm"} or config.get("schemaVersion") != 1:
        raise RuntimeResolutionError("Local toolchain config must have schemaVersion=1 and optional node/pnpm paths")
    return config, path


def _pnpm_entry(candidate):
    """Accept the actual installed pnpm JS entry, never Corepack/npx shims."""
    if not candidate.is_file():
        return None
    candidate = candidate.resolve()
    if candidate.name not in ("pnpm.cjs", "pnpm.mjs", "pnpm.js"):
        return None
    try:
        metadata = json.loads((candidate.parent.parent / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return candidate if isinstance(metadata, dict) and metadata.get("name") == "pnpm" else None


def assert_no_project_npmrc(release_root):
    """Existence-only guard: pnpm may also read project/ancestor npmrc files."""
    root = Path(release_root).resolve()
    candidates = [root / "blog" / ".npmrc", root / "ship" / ".npmrc", root / ".npmrc"]
    candidates.extend(parent / ".npmrc" for parent in root.parents)
    for candidate in candidates:
        if candidate.exists() or candidate.is_symlink():
            raise RuntimeResolutionError("Unreviewed project/ancestor .npmrc exists; refusing without reading its contents: " + str(candidate) + ". Use the clean restored development package; no config is removed automatically.")


def controlled_environment(runtime, release_root, max_old_space_size=2048):
    """No inherited npm settings/tokens; explicit public npmrc and no PM download."""
    root = Path(release_root).resolve()
    assert_no_project_npmrc(root)
    npmrc = root / "scripts" / "empty-user.npmrc"
    if not npmrc.is_file():
        raise RuntimeResolutionError("Missing controlled public npmrc: " + str(npmrc))
    if type(max_old_space_size) is not int or not 128 <= max_old_space_size <= 8192:
        raise RuntimeResolutionError("max_old_space_size must be an integer between 128 and 8192 MiB")
    allowed = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE",
               "APPDATA", "LOCALAPPDATA", "COMSPEC", "PATHEXT", "PROCESSOR_ARCHITECTURE",
               "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "TZ", "KUHAI_RELEASE_OWNER")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({
        "NPM_CONFIG_USERCONFIG": str(npmrc), "NPM_CONFIG_GLOBALCONFIG": str(npmrc),
        "npm_config_registry": "https://registry.npmjs.org/",
        "pnpm_config_pm_on_fail": "ignore", "npm_config_manage_package_manager_versions": "false",
        # pnpm 11 defaults run/exec dependency verification to an implicit install.
        # Its dedicated env override also protects nested pnpm invocations.
        "pnpm_config_verify_deps_before_run": "false",
        "npm_config_package_manager_strict": "false", "npm_config_store_dir": str(root / ".pnpm-store"),
        "COREPACK_ENABLE_NETWORK": "0", "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "CONTENT_SYNC_PULL": "false", "ASTRO_TELEMETRY_DISABLED": "1", "CI": "true",
        "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        "NODE_OPTIONS": "--max-old-space-size=" + str(max_old_space_size),
        "KUHAI_NODE": str(runtime.node), "KUHAI_PNPM": str(runtime.pnpm),
    })
    env["PATH"] = str(runtime.node.parent) + os.pathsep + env.get("PATH", "")
    return env


def _version(command, root, environment):
    try:
        result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess_flags())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeResolutionError("Installed runtime could not report its version: " + str(command[0])) from exc
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][\w.-]+)?", value):
        raise RuntimeResolutionError("Installed runtime version probe failed: " + str(command[0]) + "; exit=" + str(result.returncode))
    return value.removeprefix("v")


def resolve_runtime(release_root):
    """env > local non-release config > installed PATH/adjacent layout; no install."""
    if sys.version_info < (3, 12):
        raise RuntimeResolutionError("Python >=3.12 is required for the filesystem safety checks; no runtime installation or substitution performed")
    root = Path(release_root).resolve()
    config, config_path = _local_config(root)
    node_value = os.environ.get("KUHAI_NODE") or config.get("node")
    if node_value:
        node = _file(node_value, root, "KUHAI_NODE/node")
        node_source = "KUHAI_NODE" if os.environ.get("KUHAI_NODE") else str(config_path)
    else:
        found = shutil.which("node")
        if not found:
            raise RuntimeResolutionError("Node.js is missing. Set KUHAI_NODE to an installed executable or install Node manually; no automatic installation is performed.")
        node = Path(found).resolve()
        node_source = "PATH:node"
    pnpm_value = os.environ.get("KUHAI_PNPM") or config.get("pnpm")
    if pnpm_value:
        pnpm = _pnpm_entry(_file(pnpm_value, root, "KUHAI_PNPM/pnpm"))
        if pnpm is None:
            raise RuntimeResolutionError("KUHAI_PNPM/pnpm must point to an installed pnpm/bin/pnpm.cjs, pnpm.mjs, or pnpm.js entry (not a Corepack or command shim)")
        pnpm_source = "KUHAI_PNPM" if os.environ.get("KUHAI_PNPM") else str(config_path)
    else:
        candidates = []
        found = shutil.which("pnpm")
        if found:
            resolved = Path(found).resolve()
            candidates.append((resolved, "PATH:pnpm resolved JS entry"))
            for prefix in (resolved.parent, resolved.parent.parent):
                for suffix in ("mjs", "cjs", "js"):
                    candidates.append((prefix / "node_modules" / "pnpm" / "bin" / ("pnpm." + suffix), "installed layout beside PATH:pnpm"))
        for prefix in (node.parent, node.parent.parent, node.parent.parent / "lib"):
            for suffix in ("mjs", "cjs", "js"):
                candidates.append((prefix / "node_modules" / "pnpm" / "bin" / ("pnpm." + suffix), "installed layout beside Node"))
        pnpm, pnpm_source = None, None
        for candidate, origin in candidates:
            entry = _pnpm_entry(candidate)
            if entry:
                pnpm, pnpm_source = entry, origin
                break
        if pnpm is None:
            raise RuntimeResolutionError("Installed pnpm JS entry not found. Set KUHAI_PNPM explicitly; this command will not invoke Corepack/npx or download a package manager.")
    runtime = RuntimePaths(node=node, pnpm=pnpm, python=Path(sys.executable).resolve(),
                           sources={"node": node_source, "pnpm": pnpm_source, "python": "current Python interpreter"})
    env = controlled_environment(runtime, root, max_old_space_size=768)
    runtime.versions = {"node": _version([str(node), "--version"], root, env),
                        "pnpm": _version([str(node), str(pnpm), "--version"], root, env),
                        "python": ".".join(map(str, sys.version_info[:3]))}
    if tuple(map(int, runtime.versions["node"].split(".")[:2])) < (22, 12):
        raise RuntimeResolutionError("Node >=22.12 is required; actual " + runtime.versions["node"])
    for tool, version in {"node": "24.19.0", "pnpm": "11.25.0"}.items():
        if runtime.versions[tool] != version:
            runtime.warnings.append(tool + " differs from the actually tested baseline " + version + ": " + runtime.versions[tool] + "; no runtime installation or substitution performed")
    blog_package = root / "blog" / "package.json"
    if blog_package.is_file():
        declared = json.loads(blog_package.read_text(encoding="utf-8")).get("packageManager", "")
        runtime.versions["blogDeclaredPackageManager"] = declared
        if declared != "pnpm@" + runtime.versions["pnpm"]:
            runtime.warnings.append("Blog declares " + declared + "; using installed pnpm@" + runtime.versions["pnpm"] + ". Package declaration/lock are unchanged; automatic PM download is disabled.")
    return runtime


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(resolve_runtime(Path(__file__).resolve().parent.parent).as_dict(), ensure_ascii=False, indent=2))
    except RuntimeResolutionError as exc:
        print(json.dumps({"status": "MISSING_OR_INCOMPATIBLE_TOOLCHAIN", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
