"""Run explicitly requested pnpm commands with installed, portable runtime paths."""
import datetime
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from runtime_paths import resolve_runtime, controlled_environment, subprocess_flags, RuntimeResolutionError, PNPM_NO_AUTO_INSTALL_ARGS

RELEASE = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode")
    parser.add_argument("--project", choices=("blog", "ship"), default="blog")
    args = parser.parse_args()
    mode = args.mode
    commands = {
        "install": ["install", "--frozen-lockfile", "--ignore-scripts", "--reporter=append-only", "--network-concurrency=4", "--store-dir", str(RELEASE / ".pnpm-store")],
        "version": ["--version"], "configure": ["exec", "node", "scripts/kuhai/configure.mjs"],
        "content-validate": ["run", "content:validate"], "content-sync": ["run", "content:sync"],
        "check": ["run", "check"], "type-check": ["run", "type-check"],
        "check-manifest": ["run", "check:manifest"], "build": ["run", "build"],
    }
    if mode not in commands:
        raise RuntimeResolutionError("Expected one of: " + ", ".join(commands))
    if args.project == "ship" and mode not in ("install", "version"):
        raise RuntimeResolutionError("The ship project supports install/version here; use the release command for an explicitly pinned ship build")
    lock = RELEASE / "release-plan" / ".release.lock"
    if mode != "version" and lock.exists():
        try:
            owner = json.loads(lock.read_text(encoding="utf-8")).get("token")
        except (OSError, ValueError) as exc:
            raise RuntimeResolutionError("Cannot verify the active release lock; refusing to run pnpm") from exc
        if not owner or os.environ.get("KUHAI_RELEASE_OWNER") != owner:
            raise RuntimeResolutionError("Another release owns the build lock; wait for that release to finish before running pnpm")
    runtime = resolve_runtime(RELEASE)
    environment = controlled_environment(runtime, RELEASE, max_old_space_size=768 if mode in ("install", "version") else 2048)
    command = [*PNPM_NO_AUTO_INSTALL_ARGS, *commands[mode]]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (RELEASE / "evidence").mkdir(exist_ok=True)
    log = RELEASE / "evidence" / f"pnpm-{args.project}-{mode}-{stamp}.log"
    print(json.dumps({"mode": mode, "project": args.project, "toolchain": runtime.as_dict()}, ensure_ascii=False), flush=True)
    with log.open("x", encoding="utf-8") as output:
        output.write(json.dumps({"toolchain": runtime.as_dict(), "command": command}, ensure_ascii=False) + "\n")
        output.flush()
        process = subprocess.Popen([str(runtime.node), str(runtime.pnpm), *command], cwd=RELEASE / args.project, env=environment,
                                   stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess_flags())
        print(json.dumps({"pid": process.pid, "log": str(log), "mode": mode}), flush=True)
        try:
            result = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            raise RuntimeResolutionError("Owned package command exceeded 900 seconds")
    print(json.dumps({"exit_code": result, "log": str(log)}), flush=True)
    return result

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except RuntimeResolutionError as exc:
        print(json.dumps({"status": "TOOLCHAIN_OR_RELEASE_LOCK_ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
