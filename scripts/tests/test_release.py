"""Focused release safety tests; temporary fixtures only, no actual site build."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("kuhai_release_tested", Path(__file__).resolve().parents[1] / "release.py")
release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = release
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kuhai-release-test-")
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = "public-p26p27-final-20261022-r1/snapshot.json"
        self.write("site.json", '{"public":"fixture"}\n')
        self.write("ship/src/app.mjs", "export const fixture = 1;\n")
        self.write("开发与发布说明-v2.txt", "Temporary fixture developer instructions.\n")
        handoff = self.write("ship/public-p26p27-final-20261022-r1/handoff-evidence/handoff.json", '{"kind":"test handoff"}')
        self.write("ship/" + self.snapshot, release.json_text({"source": release.SOURCE, "evidence": [], "handoffSha256": release.fingerprint(handoff)["sha256"]}))
        snapshot_sha = release.fingerprint(self.root / "ship" / self.snapshot)["sha256"]
        patch = mock.patch.object(release, "SNAPSHOT_SHA", snapshot_sha)
        patch.start()
        self.addCleanup(patch.stop)
        self.write("ship/dist-baseline/index.html", "<html>Fixture</html>\n")
        row = {"path": "index.html", **release.fingerprint(self.root / "ship/dist-baseline/index.html")}
        manifest = {"schema": "ship-release-build-v1", "sourceStage": release.SOURCE["stage"], "sourceSceneSha256": release.SOURCE["sha256"], "snapshot": self.snapshot, "snapshotSha256": snapshot_sha, "output": "dist-baseline", "siteConfigSha256": release.fingerprint(self.root / "site.json")["sha256"], "assets": [row]}
        self.write("ship/build-manifest-dist-baseline.json", release.json_text(manifest))
        self.plan = {"schema": "kuhai-local-release-plan-v1", "source": release.SOURCE, "snapshot": self.snapshot, "snapshotSha256": snapshot_sha,
                     "baselineShip": {"directory": "ship/dist-baseline", "manifest": "ship/build-manifest-dist-baseline.json", "manifestSha256": release.fingerprint(self.root / "ship/build-manifest-dist-baseline.json")["sha256"]},
                     "sharedInputFiles": ["site.json"], "sharedInputDirectories": ["ship/src"], "deploymentManifest": "deployment/DELIVERY-SHA256-v3.json"}
        self.plan["baselineSharedInputs"] = release.shared_inputs(self.root, self.plan)
        deployment_file = self.write("deployment/preflight.py", "# temporary test fixture\n")
        self.write("deployment/DELIVERY-SHA256-v3.json", release.json_text({"files": [{"path": "preflight.py", **release.fingerprint(deployment_file)}]}))
        self.write(release.PLAN, release.json_text(self.plan))
        (self.root / "evidence").mkdir()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_new_deployment_manifest_default_override_and_integrity(self):
        original_plan = (self.root / release.PLAN).read_bytes()
        current = self.root / "deployment/DELIVERY-SHA256-v3.json"
        self.write("deployment/DELIVERY-SHA256-v4.json", current.read_text())
        _, record, _ = release.plan_release(self.root, "deployment-current", "auto", None)
        self.assertEqual(record["deploymentManifest"]["path"], "deployment/DELIVERY-SHA256-v4.json")
        self.write("deployment/DELIVERY-SHA256-v5.json", current.read_text())
        _, newest, _ = release.plan_release(self.root, "deployment-newest", "auto", None)
        self.assertEqual(newest["deploymentManifest"]["path"], "deployment/DELIVERY-SHA256-v5.json")
        _, fourth, _ = release.plan_release(self.root, "deployment-fourth", "auto", None, deployment_manifest="deployment/DELIVERY-SHA256-v4.json")
        self.assertEqual(fourth["deploymentManifest"]["path"], "deployment/DELIVERY-SHA256-v4.json")
        _, legacy, _ = release.plan_release(self.root, "deployment-legacy", "auto", None, deployment_manifest="deployment/DELIVERY-SHA256-v3.json")
        self.assertEqual(legacy["deploymentManifest"]["path"], "deployment/DELIVERY-SHA256-v3.json")
        self.assertEqual(original_plan, (self.root / release.PLAN).read_bytes())
        self.write("deployment/preflight.py", "changed after manifest")
        with self.assertRaisesRegex(ValueError, "Deployment input differs"):
            release.plan_release(self.root, "deployment-bad", "auto", None)

    def test_unchanged_articles_and_read_only_plan(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        _, record, old = release.plan_release(self.root, "candidate-1", "auto", None)
        self.assertEqual(record["mode"], "articles")
        self.assertEqual(record["ship"]["directory"], "ship/dist-baseline")
        self.assertIsNone(old)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_changed_site_or_new_ship_source_requires_shared(self):
        for name in ["site.json", "ship/src/new.mjs"]:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes() if path.exists() else None
                self.write(name, '"Changed fixture"')
                _, record, _ = release.plan_release(self.root, "candidate-2", "auto", None)
                self.assertEqual(record["mode"], "shared")
                with self.assertRaisesRegex(ValueError, "use --mode shared"):
                    release.plan_release(self.root, "candidate-2", "articles", None)
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)

    def test_explicit_shared_does_not_fall_back(self):
        _, record, _ = release.plan_release(self.root, "candidate-3", "shared", None)
        self.assertEqual(record["mode"], "shared")
        self.assertEqual(record["snapshot"], self.snapshot)
        self.assertEqual(record["source"], release.SOURCE)

    def test_tampered_pinned_build_rejected_even_in_shared(self):
        self.write("ship/dist-baseline/index.html", "Changed")
        with self.assertRaisesRegex(ValueError, "Ship build changed"):
            release.plan_release(self.root, "candidate-4", "shared", None)

    def test_existing_version_and_invalid_paths_rejected(self):
        (self.root / "dist-candidate-5").mkdir()
        with self.assertRaises(FileExistsError):
            release.plan_release(self.root, "candidate-5", "auto", None)
        for value in ["../escape", "C:/escape", "x//y", "x/./y", "x/../y", "x\\y", "NUL.txt", "x:ads", "/absolute"]:
            with self.subTest(path=value), self.assertRaises(ValueError):
                release.relative_name(value)
        for value in ["../x", "UPPER", "-x", "x" * 49]:
            with self.subTest(version=value), self.assertRaises(ValueError):
                release.plan_release(self.root, value, "auto", None)

    def test_lock_is_exclusive_and_owned_cleanup_only(self):
        with release.exclusive_lock(self.root, "one") as token:
            lock = self.root / release.LOCK
            self.assertEqual(release.load_json(lock)["token"], token)
            with self.assertRaises(RuntimeError):
                with release.exclusive_lock(self.root, "two"):
                    self.fail("Concurrent owner entered")
            self.assertTrue(lock.exists())
        self.assertFalse(lock.exists())
        with release.exclusive_lock(self.root, "three"):
            lock.write_text('{"token":"replacement"}', encoding="utf-8")
        self.assertTrue(lock.exists(), "Must not erase a replacement owner")

    def test_hash_asset_selection_excludes_old_documents_and_workers(self):
        for name in ["blog/_astro/page.Abc_def123.js", "assets/font.12345678.woff2", "chunks/chunk-WBPJ3QFW.js", "chunks/viewer-IDBVFMMX.js.LEGAL.txt"]:
            self.assertTrue(release.hashed_asset(name), name)
        for name in ["index.html", "blog/post/index.html", "assets/state.12345678.json", "app.js", "sw.12345678.js", "blog/service-worker.12345678.js", ".env"]:
            self.assertFalse(release.hashed_asset(name), name)

    def old_release(self):
        old_dir = self.root / "dist-old"
        self.write("dist-old/blog/_astro/page.Abc_def123.js", "old hashed module")
        self.write("dist-old/index.html", "old html never copied")
        self.write("dist-old/lighting.json", '{"old":"metadata"}')
        rows = [{"path": name, **row} for name, row in release.inventory(self.root, "dist-old").items()]
        return {"output": "dist-old", "files": rows}, old_dir

    def test_retention_copies_only_verified_hash_assets(self):
        old = self.old_release()
        dest = self.root / "dist-new"
        dest.mkdir()
        report = release.retain_hashed_assets(self.root, old, dest)
        self.assertEqual(len(report["copied"]), 1)
        self.assertTrue((dest / "blog/_astro/page.Abc_def123.js").is_file())
        self.assertFalse((dest / "index.html").exists())
        self.assertFalse((dest / "lighting.json").exists())

    def test_hash_collision_never_overwrites(self):
        old = self.old_release()
        conflict = self.write("dist-new/blog/_astro/page.Abc_def123.js", "different current bytes")
        with self.assertRaisesRegex(ValueError, "collision"):
            release.retain_hashed_assets(self.root, old, self.root / "dist-new")
        self.assertEqual(conflict.read_text(), "different current bytes")

    def test_changed_old_file_does_not_enter_new_release(self):
        old = self.old_release()
        self.write("dist-old/blog/_astro/page.Abc_def123.js", "changed after evidence")
        dest = self.root / "dist-new"
        dest.mkdir()
        with self.assertRaisesRegex(ValueError, "changed during retention"):
            release.retain_hashed_assets(self.root, old, dest)
        self.assertEqual(list(dest.iterdir()), [])

    def test_no_previous_dist_is_explicit_not_certified(self):
        result = release.retain_hashed_assets(self.root, None, self.root / "missing")
        self.assertEqual(result["status"], "NO_PREVIOUS_DIST_AVAILABLE")
        self.assertFalse((self.root / "missing").exists())

    def test_first_command_failure_stops_and_preserves_evidence(self):
        plan, record, old = release.plan_release(self.root, "fail-first", "auto", None)
        runtime = types.SimpleNamespace(node="unused", versions={}, warnings=[])
        helper = types.SimpleNamespace(controlled_environment=lambda *a, **k: {})
        with mock.patch.object(release.Runner, "step", side_effect=RuntimeError("fixture failure")) as step, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(release.execute(self.root, plan, record, old, runtime, helper), 1)
        self.assertEqual(step.call_count, 1)
        self.assertEqual(step.call_args.args[0], "blog-configure")
        self.assertFalse((self.root / release.STATE).exists())
        self.assertFalse((self.root / release.LOCK).exists())
        evidence = release.load_json(self.root / "evidence/release-fail-first/run.json")
        self.assertFalse(evidence["passed"])
        self.assertIn("fixture failure", evidence["error"])

    def test_configure_race_cannot_adopt_new_ui_as_old_ship_baseline(self):
        plan, record, old = release.plan_release(self.root, "configure-race", "articles", None)
        runtime = types.SimpleNamespace(node="unused", versions={}, warnings=[])
        helper = types.SimpleNamespace(controlled_environment=lambda *a, **k: {})

        def mutate_during_configure(label, *args, **kwargs):
            self.assertEqual(label, "blog-configure")
            self.write("ship/src/app.mjs", "new UI written while configure ran")

        with mock.patch.object(release.Runner, "step", side_effect=mutate_during_configure) as step, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(release.execute(self.root, plan, record, old, runtime, helper), 1)
        self.assertEqual(step.call_count, 1)
        self.assertFalse((self.root / release.STATE).exists())
        evidence = release.load_json(self.root / "evidence/release-configure-race/run.json")
        self.assertIn("changed during configure", evidence["error"])
        self.assertNotIn("sharedInputs", evidence)

    def test_configure_may_only_update_the_three_named_generated_files(self):
        initial = {name: None for name in release.CONFIGURE_OUTPUTS}
        actual = {name: {"sha256": "test-generated"} for name in release.CONFIGURE_OUTPUTS}
        self.assertEqual(release.after_configure(initial, actual), actual)
        actual["site.json"] = {"sha256": "concurrent-site-edit"}
        with self.assertRaises(RuntimeError):
            release.after_configure(initial, actual)

    def test_old_python_is_rejected_before_any_path_or_runtime_probe(self):
        with mock.patch.object(release.sys, "version_info", (3, 11, 9)), mock.patch.object(release, "plan_release") as planner:
            with self.assertRaisesRegex(RuntimeError, "3.12"):
                release.main()
        planner.assert_not_called()

    def test_windows_reparse_attribute_is_rejected_without_following(self):
        fake_path = mock.Mock()
        fake_path.lstat.return_value = types.SimpleNamespace(st_file_attributes=1024)
        self.assertTrue(release.linked(fake_path))
        fake_path.is_symlink.assert_not_called()

    def test_empty_keep_files_are_skipped_in_author_content_only(self):
        self.write("content/posts/.keep", "")
        self.write("content/moments/.gitkeep", "")
        article = self.write("content/posts/article.md", "public author content")
        rows = release.inventory(self.root, "content")
        self.assertEqual(rows, {"posts/article.md": release.fingerprint(article)})
        # Public-tree verification must still see unexpected hidden files.
        public_rows = release.inventory(self.root, "content", hide_sensitive=False)
        self.assertIn("posts/.keep", public_rows)
        self.assertIn("moments/.gitkeep", public_rows)

    def test_nonempty_keep_and_gitkeep_remain_rejected_without_read(self):
        for name in [".keep", ".gitkeep"]:
            with self.subTest(name=name):
                marker = self.write("markers/" + name, "not an empty placeholder")
                with mock.patch.object(release, "fingerprint") as read_content:
                    with self.assertRaisesRegex(ValueError, "Unknown nonempty"):
                        release.inventory(self.root, "markers")
                    read_content.assert_not_called()
                marker.unlink()

    def test_keep_directory_and_link_are_not_placeholder_exceptions(self):
        marker = self.root / "markers/.keep"
        marker.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Only regular"):
            release.inventory(self.root, "markers")
        marker.rmdir()
        marker.write_text("")
        with mock.patch.object(release, "linked", side_effect=lambda path: path.name == ".keep"):
            with self.assertRaisesRegex(ValueError, "Linked"):
                release.inventory(self.root, "markers")

    def test_env_and_other_hidden_files_are_rejected_without_read(self):
        for name in [".env", ".env.local", ".Keep", ".credentials"]:
            with self.subTest(name=name):
                hidden = self.write("hidden-input/" + name, "")
                with mock.patch.object(release, "fingerprint") as read_content:
                    with self.assertRaisesRegex(ValueError, "hidden/private"):
                        release.inventory(self.root, "hidden-input")
                    read_content.assert_not_called()
                hidden.unlink()

    def test_four_reviewed_content_markers_are_hashed_without_changing_bytes(self):
        content = b"This directory is intentionally empty. Add only owner-approved content.\n"
        for name in release.KNOWN_CONTENT_MARKERS:
            path = self.write(name, "")
            path.write_bytes(content)
        rows = release.inventory(self.root, "content")
        self.assertEqual(len(rows), 4)
        for name in release.KNOWN_CONTENT_MARKERS:
            self.assertEqual(rows[Path(name).relative_to("content").as_posix()], release.KNOWN_CONTENT_MARKER)
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_reviewed_marker_modified_bytes_or_unlisted_path_are_rejected(self):
        content = b"This directory is intentionally empty. Add only owner-approved content.\n"
        marker = self.write("content/content/posts/.keep", "")
        marker.write_bytes(content.replace(b"empty", b"EMPTY"))
        with self.assertRaisesRegex(ValueError, "placeholder changed"):
            release.inventory(self.root, "content")
        marker.unlink()
        unexpected = self.write("content/content/other/.keep", "")
        unexpected.write_bytes(content)
        with mock.patch.object(release, "fingerprint") as read_content:
            with self.assertRaisesRegex(ValueError, "Unknown nonempty"):
                release.inventory(self.root, "content")
            read_content.assert_not_called()

    def test_check_only_does_not_invoke_a_command_or_create_outputs(self):
        runtime = types.SimpleNamespace(versions={}, sources={}, warnings=[])
        helper = types.SimpleNamespace(resolve_runtime=lambda root: runtime)
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        with mock.patch.object(release, "ROOT", self.root), mock.patch.object(release, "import_script", return_value=helper), mock.patch.object(sys, "argv", ["release.py", "--version", "dry-run", "--check-only"]), mock.patch.object(release, "execute") as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(release.main(), 0)
        execute.assert_not_called()
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_link_escape_is_rejected_if_os_allows_links(self):
        link = self.root / "linked-source"
        try:
            link.symlink_to(self.root / "ship", target_is_directory=True)
        except OSError:
            self.skipTest("OS does not permit creating this test symlink")
        with self.assertRaises(ValueError):
            release.local(self.root, "linked-source/src/app.mjs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
