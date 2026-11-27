"""Package-boundary and relocation regressions, using only the standard library."""
import importlib.util
import json
import os
import platform
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("developer_package", Path(__file__).resolve().parents[1] / "developer-package.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class DeveloperPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kuhai-devpack-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.author = self.root / "author"
        self.author.mkdir()

    def file(self, name, data=b"example"):
        path = self.author / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def source(self):
        path = self.root / "source.zip"
        package.archive_write(self.author, path, "source", {"site.json": self.file("site.json", b'{"author":"kuhai"}')}, [])
        return path

    def deps(self, source):
        path = self.root / "deps.zip"
        shim = f'NODE_PATH="{self.author.as_posix()}/blog/node_modules/.pnpm/node_modules"\n'.encode()
        files = {"blog/node_modules/.pnpm/example/node_modules/example/index.js": self.file("blog/node_modules/.pnpm/example/node_modules/example/index.js"),
                 "blog/node_modules/.bin/example": self.file("blog/node_modules/.bin/example", shim)}
        package.archive_write(self.author, path, "dependencies", files,
                              [{"path": "blog/node_modules/example", "target": "blog/node_modules/.pnpm/example/node_modules/example"}], package.sha_file(source))
        return path

    def rewrite(self, path, update, extra=None):
        with zipfile.ZipFile(path) as archive:
            files = {info.filename: archive.read(info) for info in archive.infolist()}
        manifest = json.loads(files[package.MANIFEST])
        update(manifest)
        files[package.MANIFEST] = package.json_bytes(manifest)
        result = self.root / (path.stem + "-changed.zip")
        with zipfile.ZipFile(result, "x") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(*extra)
        return result

    def test_restore_closed_links_and_relocated_shim(self):
        source = self.source()
        deps = self.deps(source)
        target = self.root / "new author directory"
        result = package.restore(source, deps, target)
        target = target.resolve()
        link = target / "blog/node_modules/example"
        def remove_fixture_link():
            if not link.resolve().is_relative_to(self.root.resolve()):
                raise AssertionError("Fixture link escaped its test directory")
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()
        self.addCleanup(remove_fixture_link)
        self.assertTrue(result["passed"])
        assets = target / "blog/public/assets"
        self.assertTrue(assets.is_dir())
        self.assertEqual(list(assets.iterdir()), [])
        self.assertEqual(result["links"], 1)
        self.assertEqual(result["relocated_shims"], 1)
        self.assertTrue((target / "blog/node_modules/example").resolve().is_relative_to(target))
        shim = (target / "blog/node_modules/.bin/example").read_text()
        self.assertIn(target.as_posix(), shim)
        self.assertNotIn(self.author.as_posix(), shim)
        self.assertNotIn(package.TOKEN, shim)

    def test_refuses_existing_even_empty_target(self):
        source = self.source()
        target = self.root / "existing"
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "new directory"):
            package.restore(source, None, target)
        self.assertEqual(list(target.iterdir()), [])

    def test_bad_archive_hash_leaves_no_target(self):
        source = self.source()
        target = self.root / "bad-hash"
        with self.assertRaisesRegex(ValueError, "SHA256"):
            package.restore(source, None, target, "0" * 64)
        self.assertFalse(target.exists())

    def test_payload_tamper_detected(self):
        changed = self.rewrite(self.source(), lambda m: m["files"][0].update(sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "SHA256"):
            package.verify_archive(changed)

    def test_duplicate_zip_entry_detected(self):
        changed = self.rewrite(self.source(), lambda m: None, ("site.json", b"wrong"))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            package.verify_archive(changed)

    def test_zip_slip_rejected_before_restore(self):
        changed = self.rewrite(self.source(), lambda m: m["files"][0].update(path="../outside"))
        with self.assertRaises(ValueError):
            package.restore(changed, None, self.root / "zip-slip")
        self.assertFalse((self.root / "zip-slip").exists())

    def test_external_link_rejected(self):
        source = self.source()
        changed = self.rewrite(self.deps(source), lambda m: m["directory_links"][0].update(target="../outside"))
        with self.assertRaises(ValueError):
            package.restore(source, changed, self.root / "external-link")
        self.assertFalse((self.root / "external-link").exists())

    def test_links_cannot_hide_inside_another_link(self):
        source = self.source()
        changed = self.rewrite(self.deps(source), lambda m: m["directory_links"].append({"path": "blog/node_modules/example/nested", "target": "blog/node_modules/.pnpm/example/node_modules/example"}))
        with self.assertRaisesRegex(ValueError, "nested"):
            package.verify_archive(changed)

    def test_os_mismatch_rejected_before_creation(self):
        source = self.source()
        changed = self.rewrite(self.deps(source), lambda m: m.update(platform={"system": "DifferentOS", "machine": platform.machine()}))
        with self.assertRaisesRegex(ValueError, "OS/architecture"):
            package.restore(source, changed, self.root / "wrong-os")
        self.assertFalse((self.root / "wrong-os").exists())

    def test_source_dependency_pair_is_bound(self):
        source = self.source()
        changed = self.rewrite(self.deps(source), lambda m: m["source_archive"].update(sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "different source"):
            package.restore(source, changed, self.root / "wrong-pair")
        self.assertFalse((self.root / "wrong-pair").exists())

    def test_credentials_excluded_without_reading(self):
        self.file("content/a.md")
        self.file("content/.env", b"DO NOT READ")
        self.file("content/.NPMRC", b"DO NOT READ")
        self.file("content/.ENV.local", b"DO NOT READ")
        self.file("content/private.key", b"DO NOT READ")
        selected, _ = package.source_files(self.author, {"trees": ["content"], "files": [], "exclude": []})
        self.assertEqual(list(selected), ["content/a.md"])

    def test_unsafe_portable_names_rejected(self):
        for name in ("/absolute", "C:/path", "a\\b", "a//b", "a/../b", "a/./b", "NUL.txt", "a. ", "a\nfile", "a?b", "a|b", "a*", "a\x7f"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.relative(name)

    def test_unsafe_shell_restore_root_rejected(self):
        for name in ("$test", "tick`test", "percent%PATH%", "a&b", "a'b"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "metacharacters"):
                package.restore(self.root / "unused.zip", None, self.root / name)
            self.assertFalse((self.root / name).exists())

    def test_windows_file_limit_counts_utf16_before_creating_target(self):
        target = self.root.resolve() / "length-check"
        prefix_units = len((str(target) + os.sep).encode("utf-16-le")) // 2
        name = "\U0001f680" + "a" * (260 - prefix_units - 2 - 4) + ".map"
        source = self.root / "long-source.zip"
        package.archive_write(self.author, source, "source", {name: self.file("payload.map")}, [])
        with patch.object(package.platform, "system", return_value="Windows"):
            package.check_windows_restore_paths(target, [{"files": [{"path": name[:-1]}], "directory_links": []}])
            with self.assertRaisesRegex(ValueError, "260 UTF-16 code units.*must be <260"):
                package.restore(source, None, target)
        self.assertFalse(target.exists())

    def test_windows_directory_and_link_limits(self):
        target = self.root.resolve() / "directory-check"
        prefix_units = len((str(target) + os.sep).encode("utf-16-le")) // 2
        directory = "d" * (248 - prefix_units)
        cases = [
            {"files": [{"path": directory + "/x"}], "directory_links": []},
            {"files": [], "directory_links": [{"path": directory, "target": "short-target"}]},
            {"files": [], "directory_links": [{"path": "short-link", "target": directory}]},
        ]
        with patch.object(package.platform, "system", return_value="Windows"):
            package.check_windows_restore_paths(target, [{"files": [{"path": directory[:-1] + "/x"}], "directory_links": []}])
            for manifest in cases:
                with self.subTest(manifest=manifest), self.assertRaisesRegex(ValueError, "248 UTF-16 code units.*must be <248"):
                    package.check_windows_restore_paths(target, [manifest])
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
