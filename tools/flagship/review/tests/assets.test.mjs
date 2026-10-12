import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { validateBytes } from 'gltf-validator';

const assets = new URL('../public/assets/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('model-manifest.json', assets)));
for (const [filename, expected] of Object.entries(manifest.files)) {
  test(`${filename}: fingerprint, glTF container and semantic groups`, async () => {
    const bytes = await readFile(new URL(filename, assets));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected.sha256);
    assert.equal(bytes.length, expected.bytes);
    const json = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString());
    assert.ok(json.extensionsRequired.includes('KHR_draco_mesh_compression'));
    assert.ok(!json.images?.length); assert.ok(!json.animations?.length);
    assert.ok(!json.cameras?.length);
    const roles = new Set(json.nodes.map(n => n.extras?.role).filter(Boolean));
    assert.deepEqual([...roles].sort(), filename === 'archive.glb' ? ['archive_interior'] : ['archive_shell','hull']);
    const tris = json.meshes.flatMap(m => m.primitives).reduce((sum, p) => sum + json.accessors[p.indices].count / 3, 0);
    assert.equal(tris, expected.triangles);
    const report = await validateBytes(new Uint8Array(bytes), { uri: filename });
    assert.equal(report.issues.numErrors, 0, JSON.stringify(report.issues));
    assert.equal(report.issues.numWarnings, 0, JSON.stringify(report.issues));
  });
}
test('web budget and protected source fingerprint are explicit', () => {
  assert.ok(manifest.files['flagship.glb'].bytes < 2000000);
  assert.ok(manifest.files['archive.glb'].bytes < 150000);
  assert.equal(manifest.source_sha256, 'e05803fd34da6ccff0fb680bf3953165aabf742bd659342f5680de1022d0e9a7');
  assert.equal(manifest.object_material_overrides_respected, true);
  assert.equal(manifest.browser_performance_tested, false);
});
