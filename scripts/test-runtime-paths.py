"""Small stdlib tests; no installation, network, build, or browser."""
import json
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runtime_paths as rp


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kuhai-runtime-test-")
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/empty-user.npmrc").write_text("registry=https://registry.npmjs.org/\n")
        self.node = self.root / "installed/bin/node.exe"
        self.node.parent.mkdir(parents=True)
        self.node.write_bytes(b"fixture-only-not-executed")
        self.pnpm = self.root / "installed/node_modules/pnpm/bin/pnpm.mjs"
        self.pnpm.parent.mkdir(parents=True)
        self.pnpm.write_text("// fixture-only-not-executed\n")
        (self.pnpm.parent.parent / "package.json").write_text(json.dumps({"name": "pnpm", "version": "11.25.0"}))
        (self.root / "blog").mkdir()
        (self.root / "blog/package.json").write_text(json.dumps({"packageManager": "pnpm@11.28.2"}))

    def tearDown(self):
        self.temp.cleanup()

    def fake_version(self, command, root, environment):
        self.assertEqual(environment["COREPACK_ENABLE_NETWORK"], "0")
        return "24.19.0" if len(command) == 2 else "11.25.0"

    def resolve(self, env, which=None):
        with patch.dict(os.environ, env, clear=True), patch.object(rp.shutil, "which", side_effect=which), patch.object(rp, "_version", side_effect=self.fake_version):
            return rp.resolve_runtime(self.root)

    def test_explicit_paths_and_declared_version_difference(self):
        r = self.resolve({"KUHAI_NODE": str(self.node), "KUHAI_PNPM": str(self.pnpm)})
        self.assertEqual(r.node, self.node.resolve())
        self.assertEqual(r.pnpm, self.pnpm.resolve())
        self.assertIn("11.28.2", r.warnings[0])

    def test_python_before_312_is_rejected_before_filesystem_or_probe(self):
        with patch.object(rp.sys, "version_info", (3, 11, 9)), patch.object(rp, "_local_config") as config, patch.object(rp.subprocess, "run") as run, patch.object(Path, "resolve") as resolve:
            with self.assertRaisesRegex(rp.RuntimeResolutionError, "Python >=3.12 is required"):
                rp.resolve_runtime(self.root)
            resolve.assert_not_called()
            config.assert_not_called()
            run.assert_not_called()

    def test_path_node_and_adjacent_installed_pnpm(self):
        r = self.resolve({}, lambda name: str(self.node) if name == "node" else None)
        self.assertEqual(r.pnpm, self.pnpm.resolve())
        self.assertEqual(r.sources["node"], "PATH:node")

    def test_relative_local_config_is_root_relative(self):
        (self.root / "toolchain-local.json").write_text(json.dumps({"schemaVersion": 1, "node": str(self.node.relative_to(self.root)), "pnpm": str(self.pnpm.relative_to(self.root))}))
        r = self.resolve({}, lambda name: None)
        self.assertEqual(r.node, self.node.resolve())

    def test_explicit_missing_tool_does_not_silently_fallback(self):
        with self.assertRaisesRegex(rp.RuntimeResolutionError, "does not exist"):
            self.resolve({"KUHAI_NODE": "missing-node"}, lambda name: str(self.node))

    def test_corepack_or_cmd_shim_is_not_executed(self):
        shim = self.root / "pnpm.cmd"
        shim.write_text("fixture")
        with self.assertRaisesRegex(rp.RuntimeResolutionError, "not a Corepack"):
            self.resolve({"KUHAI_NODE": str(self.node), "KUHAI_PNPM": str(shim)})

    def test_no_installed_node_fails_without_subprocess(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(rp.shutil, "which", return_value=None), patch.object(rp.subprocess, "run") as run:
            with self.assertRaisesRegex(rp.RuntimeResolutionError, "no automatic installation"):
                rp.resolve_runtime(self.root)
            run.assert_not_called()

    def test_controlled_environment_discards_inherited_npm_settings(self):
        r = rp.RuntimePaths(self.node, self.pnpm, Path(__file__))
        with patch.dict(os.environ, {"NPM_TOKEN": "fixture-never-propagate", "npm_config_userconfig": "fixture-private-config", "NODE_OPTIONS": "fixture-option", "PATH": "test-path", "KUHAI_RELEASE_OWNER": "fixture-owner"}, clear=True):
            env = rp.controlled_environment(r, self.root, max_old_space_size=768)
        self.assertNotIn("NPM_TOKEN", env)
        self.assertNotIn("npm_config_userconfig", env)
        self.assertEqual(env["NPM_CONFIG_USERCONFIG"], str(self.root.resolve() / "scripts/empty-user.npmrc"))
        self.assertEqual(env["NODE_OPTIONS"], "--max-old-space-size=768")
        self.assertEqual(env["KUHAI_RELEASE_OWNER"], "fixture-owner")
        self.assertEqual(env["KUHAI_NODE"], str(self.node))

    def test_posix_subprocess_flags_are_zero(self):
        with patch.object(rp.os, "name", "posix"):
            self.assertEqual(rp.subprocess_flags(), 0)

    def test_controlled_environment_disables_pnpm_implicit_install(self):
        r = rp.RuntimePaths(self.node, self.pnpm, Path(__file__))
        with patch.dict(os.environ, {"pnpm_config_verify_deps_before_run": "install"}, clear=True):
            env = rp.controlled_environment(r, self.root)
        self.assertEqual(env["pnpm_config_verify_deps_before_run"], "false")

    def test_wrapper_disables_implicit_install_but_retains_explicit_install(self):
        spec = importlib.util.spec_from_file_location("run_pnpm_test", Path(__file__).with_name("run-pnpm.py"))
        wrapper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wrapper)
        r = rp.RuntimePaths(self.node, self.pnpm, Path(__file__))
        for mode in ("configure", "build", "install"):
            with self.subTest(mode=mode), patch.object(wrapper, "RELEASE", self.root), patch.object(wrapper, "resolve_runtime", return_value=r), patch.object(wrapper.sys, "argv", ["run-pnpm.py", mode]), patch.object(wrapper.sys, "stdout", io.StringIO()), patch.object(wrapper.subprocess, "Popen") as popen:
                popen.return_value.pid = 123
                popen.return_value.wait.return_value = 0
                self.assertEqual(wrapper.main(), 0)
                command = popen.call_args.args[0]
                self.assertEqual(command[2], "--config.verify-deps-before-run=false")
                self.assertEqual(popen.call_args.kwargs["env"]["pnpm_config_verify_deps_before_run"], "false")
                if mode == "install":
                    self.assertEqual(command[3], "install")
                    self.assertIn("--frozen-lockfile", command)
                    self.assertIn("--ignore-scripts", command)
                else:
                    self.assertNotIn("install", command)

    def test_project_npmrc_is_rejected_without_reading_it(self):
        (self.root / "blog/.npmrc").write_text("fixture-not-to-be-read")
        r = rp.RuntimePaths(self.node, self.pnpm, Path(__file__))
        with patch.object(Path, "read_text", side_effect=AssertionError("no file content should be read")):
            with self.assertRaisesRegex(rp.RuntimeResolutionError, "without reading"):
                rp.controlled_environment(r, self.root)


if __name__ == "__main__":
    unittest.main()
