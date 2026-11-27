"""Small offline deployment integration checks; no build, archive or network."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('deployment_package_tested', ROOT / 'scripts/package-delivery.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class DeploymentDeliveryTests(unittest.TestCase):
    def test_current_manifest_payload_and_developer_policy_match(self):
        name = 'deployment/DELIVERY-SHA256-v5.json'
        manifest = json.loads((ROOT / name).read_text(encoding='utf-8'))
        policy = json.loads((ROOT / 'scripts/developer-package-policy.json').read_text(encoding='utf-8'))
        self.assertIn(name, policy['files'])
        self.assertIn('deployment/server-check.py', policy['files'])
        self.assertTrue(set(package.DEPLOYMENT_FILES) | {'server-check.py'} <= {row['path'] for row in manifest['files']})
        for row in manifest['files']:
            with self.subTest(path=row['path']):
                data = (ROOT / 'deployment' / row['path']).read_bytes()
                self.assertEqual(len(data), row['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
        previous = (ROOT / 'deployment' / manifest['previous_manifest']).read_bytes()
        self.assertEqual(hashlib.sha256(previous).hexdigest(), manifest['previous_manifest_sha256'])

    def test_packager_uses_v5_then_v4_then_legacy(self):
        with tempfile.TemporaryDirectory(prefix='kuhai-deployment-selection-') as tmp:
            root = Path(tmp)
            (root / 'deployment').mkdir()
            with mock.patch.object(package, 'RELEASE', root):
                self.assertEqual(package.default_deployment_manifest(), 'deployment/DELIVERY-SHA256-v3.json')
                (root / 'deployment/DELIVERY-SHA256-v4.json').write_text('{}')
                self.assertEqual(package.default_deployment_manifest(), 'deployment/DELIVERY-SHA256-v4.json')
                (root / 'deployment/DELIVERY-SHA256-v5.json').write_text('{}')
                self.assertEqual(package.default_deployment_manifest(), 'deployment/DELIVERY-SHA256-v5.json')

    def test_portable_guide_retains_http_tool_and_failure_limits(self):
        text = (ROOT / 'deployment/部署与更新说明.txt').read_text(encoding='utf-8-sig')
        portable = package.portable_deployment_guide(text).decode('utf-8')
        self.assertIn('python3 deployment/server-check.py --origin', portable)
        self.assertIn('--manifest MANIFEST.json', portable)
        self.assertIn('失败', portable)
        self.assertNotIn('截至 v2 的已读交付证据', portable)
        self.assertNotIn('DELIVERY-SHA256', portable)


if __name__ == '__main__':
    unittest.main()
