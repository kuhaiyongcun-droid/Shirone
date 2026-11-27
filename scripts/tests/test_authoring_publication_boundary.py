"""Draft-preview publication guards; small temporary files, no site build or server."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assemble = load("authoring_boundary_assemble", "assemble.py")
delivery = load("authoring_boundary_delivery", "package-delivery.py")
development = load("authoring_boundary_development", "developer-package.py")


class AuthoringPublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kuhai-authoring-boundary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for module in (assemble, delivery):
            patch = mock.patch.object(module, "RELEASE", self.root)
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name, data=b"fixture"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def marker(self, directory):
        # Malformed/empty markers are still sufficient to prohibit publication.
        return self.write(directory + "/PREVIEW-ONLY.json", b"not valid JSON")

    def test_private_roots_rejected_without_markers(self):
        for directory in ("authoring-private/article/images", "preview-work/demo/dist/blog"):
            self.write(directory + "/index.html")
            for module in (assemble, delivery):
                with self.subTest(module=module.__name__, directory=directory):
                    with self.assertRaisesRegex(ValueError, "Private authoring/preview"):
                        module.reject_preview_input(self.root / directory)

    def test_marker_on_input_or_ancestor_rejects_renamed_preview(self):
        self.write("blog/dist-reviewed-copy/index.html")
        for directory in ("blog/dist-reviewed-copy", "blog"):
            marker = self.marker(directory)
            for module in (assemble, delivery):
                with self.subTest(module=module.__name__, directory=directory):
                    with self.assertRaisesRegex(ValueError, "Preview-only marker"):
                        module.reject_preview_input(self.root / "blog/dist-reviewed-copy")
            marker.unlink()

    def test_nested_marker_cannot_be_included_as_an_ordinary_json_asset(self):
        source = self.write("blog/dist-reviewed/index.html").parent
        self.marker("blog/dist-reviewed/images/draft")
        with self.assertRaisesRegex(ValueError, "Preview-only marker"):
            assemble.collect(source, "blog", [])
        target = self.write("dist-reviewed/index.html").parent
        self.marker("dist-reviewed/blog")
        with self.assertRaisesRegex(ValueError, "Preview-only marker"):
            delivery.actual_files(target)

    def test_recognized_receipt_rejects_copy_even_without_primary_marker(self):
        self.write("blog/dist-copy/index.html")
        for payload in (b'{"schema":"kuhai-draft-preview-receipt-v1","previewOnly":true}', b"damaged receipt"):
            self.write("blog/dist-copy/draft-preview-receipt.json", payload)
            for module in (assemble, delivery):
                with self.subTest(module=module.__name__, payload=payload):
                    with self.assertRaisesRegex(ValueError, "Preview-only marker/receipt"):
                        module.reject_preview_input(self.root / "blog/dist-copy")

    def test_regular_release_is_not_rejected_by_name_or_neighbor_preview(self):
        source = self.write("blog/dist-preview-approved/index.html").parent
        self.write("blog/dist-preview-approved/images/cover.webp")
        self.marker("preview-work/isolated")
        self.assertEqual(assemble.source_root("blog/dist-preview-approved", "blog"), source)
        exclusions = []
        files = assemble.collect(source, "blog", exclusions)
        self.assertEqual({relative.as_posix() for _, relative in files}, {"index.html", "images/cover.webp"})
        self.assertEqual(exclusions, [])
        target = self.write("dist-approved/index.html").parent
        self.write("dist-approved/blog/index.html")
        self.assertEqual(set(delivery.actual_files(target)), {"index.html", "blog/index.html"})

    def run_cli(self, script, args):
        destination = self.root / "scripts" / script
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(SCRIPTS / script, destination)
        return subprocess.run([sys.executable, "-B", destination, *args], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", timeout=20)

    def test_assemble_cli_rejects_marked_copy_before_creating_output(self):
        self.write("site.json", b'{"site":{"url":"https://kuhaiyongcun.com","blogBase":"/blog/"}}')
        self.write("ship/dist/index.html")
        self.write("blog/dist/index.html")
        self.marker("blog/dist")
        result = self.run_cli("assemble.py", ["--out", "dist-candidate"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preview-only marker", result.stderr)
        self.assertFalse((self.root / "dist-candidate").exists())
        self.assertFalse((self.root / "evidence").exists())

    def test_package_cli_rejects_marked_copy_before_reading_assembly_or_making_zip(self):
        self.write("dist-candidate/index.html")
        self.marker("dist-candidate")
        result = self.run_cli("package-delivery.py", ["--dist", "dist-candidate", "--assembly-report",
                              "evidence/not-created.json", "--report", "not-created.txt", "--package", "kuhai-candidate"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preview-only marker", result.stderr)
        self.assertFalse((self.root / "delivery-packages").exists())
        self.assertFalse((self.root / "evidence").exists())

    def test_private_draft_cannot_be_used_as_a_delivery_document(self):
        path = self.write("authoring-private/unpublished/post.md", b"private draft fixture")
        with self.assertRaisesRegex(ValueError, "Private authoring/preview"):
            delivery.local_path(path)

    def test_developer_policy_carries_templates_but_excludes_private_trees(self):
        policy = json.loads((SCRIPTS / "developer-package-policy.json").read_text(encoding="utf-8"))
        self.assertIn("authoring/templates", policy["trees"])
        self.assertIn("authoring/写作指南.txt", policy["files"])
        for private in ("authoring-private", "preview-work"):
            self.assertIn(private, policy["exclude"])
        self.write("authoring/templates/post.md")
        self.write("authoring/写作指南.txt")
        self.write("authoring-private/article/post.md")
        self.write("authoring-private/article/images/photo.webp")
        self.write("preview-work/example/dist/blog/index.html")
        fixture_policy = {"files": ["authoring/写作指南.txt"],
                          "trees": ["authoring/templates", "authoring-private", "preview-work"],
                          "exclude": policy["exclude"]}
        files, _ = development.source_files(self.root, fixture_policy)
        self.assertEqual(set(files), {"authoring/templates/post.md", "authoring/写作指南.txt"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
