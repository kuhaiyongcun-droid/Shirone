"""Create private drafts, check images, preview, or explicitly prepare a local post."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from release import exclusive_lock
from runtime_paths import controlled_environment, resolve_runtime, subprocess_flags

ROOT = Path(__file__).resolve().parents[1]


def invoke(argv, environment=None):
    process = subprocess.Popen([str(value) for value in argv], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                               creationflags=subprocess_flags())
    try:
        stdout, stderr = process.communicate()
        sys.stdout.write(stdout)
        sys.stderr.write(stderr)
        return process.returncode
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create a private draft; never overwrites a file")
    new.add_argument("slug")
    new.add_argument("--title", required=True)
    new.add_argument("--template", choices=("note", "technical"), default="note")
    check = commands.add_parser("check", help="Check a private draft and its images")
    check.add_argument("slug")
    ready = commands.add_parser("prepare-publish", help="Explicitly copy an approved draft into local publication sources")
    ready.add_argument("slug")
    preview = commands.add_parser("preview", help="Build an isolated draft preview and serve it on localhost")
    preview.add_argument("slug")
    preview.add_argument("--version", required=True)
    preview.add_argument("--port", type=int, default=4180)
    preview.add_argument("--no-start", action="store_true")
    start = commands.add_parser("preview-start", help="Serve an already built private preview")
    start.add_argument("version")
    start.add_argument("--port", type=int, default=4180)
    commands.add_parser("preview-stop", help="Stop only the recorded draft-preview server")
    commands.add_parser("preview-status", help="Read the draft-preview server state")
    args = parser.parse_args()
    if args.command.startswith("preview"):
        # Keep the preview lock owner and its writer in this same process.
        # Interrupting a wrapper subprocess must not orphan a Node build.
        from draft_preview import main as preview_main
        if args.command == "preview":
            status = preview_main(["build", args.slug, "--version", args.version])
            if status or args.no_start:
                return status
            return preview_main(["start", args.version, "--port", str(args.port)])
        if args.command == "preview-start":
            return preview_main(["start", args.version, "--port", str(args.port)])
        return preview_main([args.command.removeprefix("preview-")])
    runtime = resolve_runtime(ROOT)
    environment = controlled_environment(runtime, ROOT, max_old_space_size=768)
    argv = [runtime.node, ROOT / "blog/scripts/kuhai/writing.mjs", args.command, args.slug]
    if args.command == "new":
        argv.extend(["--title", args.title, "--template", args.template])
    if args.command == "prepare-publish":
        with exclusive_lock(ROOT, "prepare-publish-" + args.slug) as token:
            environment["KUHAI_RELEASE_OWNER"] = token
            return invoke(argv, environment)
    return invoke(argv, environment)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
