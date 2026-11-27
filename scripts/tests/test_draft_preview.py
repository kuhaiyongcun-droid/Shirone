"""Isolated fixtures only: no Astro build, browser, installation or live preview."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import draft_preview as preview


class DraftPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kuhai-draft-unit-")
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.assertTrue(self.root.name.startswith("kuhai-draft-unit-"))
        # Remove only fixture links first; avoid dangling junction traversal while
        # the temporary directory later removes its ordinary source directories.
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            for name in dirs[:]:
                target = Path(directory) / name
                if preview.release_tools.linked(target):
                    self.assertTrue(target.absolute().is_relative_to(self.root))
                    dirs.remove(name)
                    if target.is_symlink():
                        target.unlink()
                    else:
                        os.rmdir(target)
        self.temporary.cleanup()

    def put(self, path, text="fixture"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def source(self):
        for name in preview.BLOG_FILES:
            self.put("blog/" + name, "export default {};" if name == "astro.config.mjs" else "{}")
        for name in ("blog/src/pages/index.astro", "blog/src/content/obsolete.md", "blog/src/user/user-config.ts", "blog/src/generated/icons.ts",
                     "blog/src/assets/fonts/font.ttf", "blog/src/data/anime.ts", "blog/scripts/content/sync.mjs", "blog/public/favicon/favicon.svg",
                     "blog/public/images/obsolete.png", "content/public/images/known.png", "content/config/site.yaml", "content/content/posts/live.md",
                     "authoring-private/draft/post.md", "scripts/filing.mjs", "site.json"):
            self.put(name)
        self.put("blog/.env", "MUST NOT READ")
        self.put("blog/src/assets/fonts/.subset/cache.txt", "old cache")
        self.put("blog/dist/index.html", "old production output")

    def ready(self):
        snapshot = self.root / "preview-work/one"
        snapshot.mkdir(parents=True)
        preview.write_marker(snapshot, "one")
        self.put("preview-work/one/blog/dist/posts/draft/index.html", '<html><head></head><body><main id="swup-container"><article>draft body</article></main></body></html>')
        self.put("preview-work/one/blog/dist/index.html", '<html><head></head><body><main id="swup-container">index</main></body></html>')
        outputs = preview.finalize(snapshot, "one", "草稿", "/blog/posts/draft/")
        record = {"schema": preview.RECEIPT_SCHEMA, "previewOnly": True, "passed": True, "version": "one", "route": "/blog/posts/draft/", "outputs": outputs}
        preview.atomic_json(snapshot / preview.RECEIPT, record)
        return snapshot

    def test_names_and_ports_cannot_target_old_previews_or_escape(self):
        for value in ("../root", "a/b", "a\\b", "CON", "x.", "x ", "", "A"):
            with self.assertRaises(ValueError):
                preview.safe_name(value)
        for value in (4175, 4177, 80, 65536):
            with self.assertRaises(ValueError):
                preview.port_number(value)
        self.assertEqual(preview.port_number(4180), 4180)

    def test_source_copy_has_private_caches_and_materialized_content_boundaries(self):
        self.source()
        snapshot = self.root / "preview-work/one"
        snapshot.mkdir(parents=True)
        before = preview.source_inventory(self.root, "draft")
        preview.copy_inputs(self.root, snapshot)
        self.assertEqual(preview.source_inventory(self.root, "draft"), before)
        for absent in ("blog/.env", "blog/src/content/obsolete.md", "blog/src/user/user-config.ts", "blog/src/generated/icons.ts",
                       "blog/src/assets/fonts/.subset/cache.txt", "blog/public/images/obsolete.png", "blog/dist"):
            self.assertFalse((snapshot / absent).exists(), absent)
        self.assertTrue((snapshot / "blog/public/favicon/favicon.svg").is_file())
        config = (snapshot / "blog/astro.config.mjs").read_text(encoding="utf-8")
        self.assertIn("fileURLToPath", config)
        self.assertIn("./.draft-cache/vite/", config)
        self.assertIn('cacheDir: fileURLToPath(new URL("./.draft-cache/astro/"', config)

    def test_source_inventory_detects_formal_output_changes(self):
        self.source()
        before = preview.source_inventory(self.root, "draft")
        self.put("blog/dist/index.html", "changed")
        self.assertNotEqual(before, preview.source_inventory(self.root, "draft"))

    def test_dependency_facade_has_its_own_cache_container(self):
        for package in ("astro", "yaml", "pagefind", "@test/library"):
            self.put("blog/node_modules/" + package + "/package.json", "{}")
        self.put("blog/node_modules/.astro/data-store.json", "canonical cache")
        self.put("blog/node_modules/.vite/metadata.json", "canonical cache")
        snapshot = self.root / "preview-work/one"
        (snapshot / "blog").mkdir(parents=True)
        links = preview.dependency_facade(self.root, snapshot)
        self.assertEqual(len(links), 4)
        self.assertFalse(preview.release_tools.linked(snapshot / "blog/node_modules"))
        self.assertFalse((snapshot / "blog/node_modules/.astro").exists())
        self.assertTrue(preview.release_tools.linked(snapshot / "blog/node_modules/astro"))
        self.assertEqual((self.root / "blog/node_modules/.astro/data-store.json").read_text(), "canonical cache")

    def test_dependency_facade_rejects_a_package_outside_author_root(self):
        target = self.put("elsewhere/package.json", "{}").parent
        (self.root / "blog/node_modules").mkdir(parents=True)
        preview.create_directory_link(target, self.root / "blog/node_modules/escape")
        snapshot = self.root / "preview-work/one"
        (snapshot / "blog").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "escapes"):
            preview.dependency_facade(self.root, snapshot)

    def test_decoration_is_inside_swup_and_escapes_untrusted_title(self):
        document = '<html><head><meta name="robots" content="index"></head><body><main id="swup-container"><article>正文</article></main></body></html>'
        result = preview.decorate_html(document, '<script>"x"</script>')
        self.assertIn('<main id="swup-container"><aside data-kuhai-draft-preview', result)
        self.assertIn('noindex,nofollow,noarchive', result)
        self.assertNotIn('content="index"', result)
        self.assertNotIn('<script>', result)
        self.assertIn('data-pagefind-ignore', result)
        with self.assertRaises(ValueError):
            preview.decorate_html(result, "again")

    def test_all_preview_output_levels_are_marked_and_receipt_binds_files(self):
        snapshot = self.ready()
        for directory in (snapshot, snapshot / "blog/dist", snapshot / "dist", snapshot / "dist/blog"):
            self.assertTrue((directory / preview.MARKER).is_file())
        actual, receipt = preview.ready_snapshot(self.root, "one")
        self.assertEqual(actual, snapshot)
        self.assertTrue(receipt["previewOnly"])
        self.assertIn("Disallow: /", (snapshot / "dist/robots.txt").read_text())

    def test_astro_redirect_stub_keeps_redirect_and_gets_private_notice(self):
        document = '<!doctype html><title>Redirecting</title><meta http-equiv="refresh" content="2;url=/blog/404.html"><body><a href="/blog/404.html">Continue</a></body>'
        result = preview.decorate_html(document, "Draft")
        self.assertIn('noindex,nofollow,noarchive', result)
        self.assertIn('content="2;url=/blog/404.html"', result)
        self.assertIn('<body><aside data-kuhai-draft-preview', result)

    def test_changed_or_failed_preview_cannot_be_started(self):
        snapshot = self.ready()
        self.put("preview-work/one/dist/blog/index.html", "tampered")
        with self.assertRaisesRegex(ValueError, "changed"):
            preview.ready_snapshot(self.root, "one")
        receipt = json.loads((snapshot / preview.RECEIPT).read_text(encoding="utf-8"))
        receipt["passed"] = False
        preview.atomic_json(snapshot / preview.RECEIPT, receipt)
        with self.assertRaisesRegex(ValueError, "completed"):
            preview.ready_snapshot(self.root, "one")

    def test_export_requires_a_single_success_json(self):
        log = self.put("export.log", '{}\n' + json.dumps({"passed": True, "route": "/blog/posts/draft/"}, indent=2) + '\n')
        self.assertTrue(preview.parse_export_log(log)["passed"])
        log.write_text('{}\nextra noise\n{"passed":true}\n')
        with self.assertRaises(ValueError):
            preview.parse_export_log(log)

    def test_known_credential_names_are_rejected_before_fingerprinting(self):
        for name in ("credentials", "id_rsa", "id_ed25519", ".env", ".npmrc"):
            path = self.put("private/" + name, "synthetic fixture, not a credential")
            with patch.object(preview.release_tools, "fingerprint") as fingerprint:
                with self.assertRaisesRegex(ValueError, "Private/config filename"):
                    preview.safe_files(self.root, "private")
                fingerprint.assert_not_called()
            path.unlink()

    def test_existing_version_is_never_reused(self):
        self.put("preview-work/one/owned.txt")
        with patch.object(preview, "resolve_runtime") as runtime:
            with self.assertRaisesRegex(ValueError, "already exists"):
                preview.build(self.root, "draft", "one")
            runtime.assert_not_called()

    def test_cancel_waits_for_owned_child_before_raising(self):
        child = Mock()
        child.wait.side_effect = [KeyboardInterrupt(), subprocess.TimeoutExpired("node", 1), 0]
        child.poll.side_effect = [None, None, 0]
        with patch.object(preview.subprocess, "Popen", return_value=child):
            with self.assertRaises(KeyboardInterrupt):
                preview.execute(["node", "fixture"], self.root, {}, self.root / "cancel.log")
        self.assertEqual(child.wait.call_count, 3)
        child.terminate.assert_not_called()

    def test_failed_step_stops_without_a_success_receipt(self):
        child = Mock()
        child.wait.return_value = 7
        with patch.object(preview.subprocess, "Popen", return_value=child):
            with self.assertRaisesRegex(RuntimeError, "exit 7"):
                preview.execute(["node", "fixture"], self.root, {}, self.root / "failed.log")

    def test_timeout_waits_for_owned_writer_without_killing_node(self):
        child = Mock()
        child.wait.side_effect = [subprocess.TimeoutExpired("node", 900), 0]
        child.poll.side_effect = [None, 0]
        with patch.object(preview.subprocess, "Popen", return_value=child):
            with self.assertRaisesRegex(RuntimeError, "has now exited"):
                preview.execute(["node", "fixture"], self.root, {}, self.root / "timeout.log")
        child.terminate.assert_not_called()
        child.kill.assert_not_called()
        self.assertIn('"timedOut": true', (self.root / "timeout.log").read_text())

    def test_startup_state_error_or_interrupt_cleans_only_new_owned_child(self):
        snapshot = self.ready()
        self.put("scripts/draft_preview.py", "fixture")
        for error in (ValueError("bad state"), KeyboardInterrupt()):
            child = Mock(pid=123)
            child.poll.side_effect = [None, None, 0]
            child.wait.return_value = 0
            with patch.object(preview.socket, "socket"), patch.object(preview.subprocess, "Popen", return_value=child), patch.object(preview, "read_state", side_effect=error):
                with self.assertRaises(type(error)):
                    preview.start(self.root, "one", 4180)
            child.terminate.assert_called_once_with()
            child.wait.assert_called_once_with(timeout=1)
            child.kill.assert_not_called()
        self.assertTrue((snapshot / preview.RECEIPT).is_file())

    def test_successful_start_leaves_its_server_running(self):
        self.ready()
        self.put("scripts/draft_preview.py", "fixture")
        child = Mock(pid=123)
        record = {"pid": 123, "status": "RUNNING"}
        with patch.object(preview.socket, "socket"), patch.object(preview.subprocess, "Popen", return_value=child), patch.object(preview, "read_state", return_value=record), patch.object(preview, "health", return_value=True), patch.object(preview, "status", return_value={"status": "RUNNING"}):
            self.assertEqual(preview.start(self.root, "one", 4180)["status"], "RUNNING")
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_private_server_records_and_sources_are_not_http_paths(self):
        self.put("scripts/serve-preview.py", (SCRIPTS / "serve-preview.py").read_text(encoding="utf-8"))
        snapshot = self.ready()
        handler = preview.preview_handler(self.root, snapshot / "dist", "one", "a" * 32, 4180)
        instance = handler.__new__(handler)
        for path in ("/PREVIEW-ONLY.json", "/blog/PREVIEW-ONLY.json", "/draft-preview-receipt.json", "/../site.json", "/blog/src/post.md"):
            with self.assertRaises((PermissionError, ValueError)):
                instance.safe_path(path)
        self.assertEqual(instance.safe_path("/blog/posts/draft/"), snapshot / "dist/blog/posts/draft")

    def test_unverified_server_stop_does_not_kill_a_process(self):
        self.put(preview.STATE, json.dumps({"schema": "kuhai-draft-preview-process-v1", "token": "a" * 32, "version": "one", "port": 4180, "pid": 9999, "status": "RUNNING"}))
        with patch.object(preview, "health", return_value=False), patch.object(preview.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
                preview.stop(self.root)
            popen.assert_not_called()
        self.assertTrue((self.root / preview.STATE).is_file())

    def test_main_has_an_integer_returncode_for_the_shared_wrapper(self):
        with patch.object(preview, "dispatch", return_value={"status": "NOT_STARTED"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(preview.main(["status"]), 0)
        with patch.object(preview, "dispatch", side_effect=ValueError("fixture")), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(preview.main(["status"]), 1)


if __name__ == "__main__":
    unittest.main()
