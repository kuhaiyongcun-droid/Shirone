/** Existing-loader integration only. No camera, renderer or animation loop.
 * Call dispose() when leaving the ship. Browser/Three integration is pending.
 */
const owners = new WeakMap();
export async function attachServiceLighting({ loader, shipRoot, profile, modelSha256, lightUrl, intensityScale, group = 'all', signal }) {
  if (!loader?.loadAsync || !shipRoot?.add || !shipRoot?.remove || !shipRoot?.traverse) throw new Error('Existing GLTFLoader and ship root required');
  if (profile?.revision !== 'fore-lighting-10' || profile.model_sha256 !== modelSha256 || profile.light_count !== 6) throw new Error('Lighting profile/model mismatch');
  if (!Number.isFinite(intensityScale) || intensityScale <= 0) throw new Error('Calibrated host intensityScale required');
  if (!['all', 'bridge', 'fore'].includes(group)) throw new Error('Unknown lighting group');
  if (owners.has(shipRoot)) throw new Error('Dispose the previous light rig first');
  if (signal?.aborted) throw new Error('Lighting attachment cancelled');
  const settings = new Map(profile.lights.map(x => [x.id, x]));
  if (settings.size !== 6) throw new Error('Duplicate or missing light definitions');
  owners.set(shipRoot, {});
  let gltf, attached = false, disposed = false;
  const meshes = [], lights = [];
  function dispose() {
    if (disposed) return;
    disposed = true;
    if (attached) shipRoot.remove(gltf.scene);
    for (const light of lights) light.shadow?.dispose?.();
    for (const [mesh, cast, receive] of meshes) { mesh.castShadow = cast; mesh.receiveShadow = receive; }
    owners.delete(shipRoot);
    signal?.removeEventListener('abort', dispose);
  }
  function setGroup(value) {
    if (disposed) throw new Error('Light rig is disposed');
    if (!['all', 'bridge', 'fore'].includes(value)) throw new Error('Unknown lighting group');
    for (const light of lights) light.visible = value === 'all' || light.userData.service_group === value;
  }
  try {
    gltf = await loader.loadAsync(lightUrl);
    gltf.scene.traverse(o => { if (o.isLight) lights.push(o); });
    if (signal?.aborted) throw new Error('Lighting attachment cancelled');
    const ids = new Set(lights.map(o => o.userData.service_light_id));
    if (lights.length !== 6 || ids.size !== 6 || lights.some(o => !settings.has(o.userData.service_light_id))) throw new Error('Unexpected light asset');
    for (const light of lights) {
      const row = settings.get(light.userData.service_light_id);
      if (row.group !== light.userData.service_group) throw new Error('Light group mismatch');
      light.intensity *= intensityScale; light.castShadow = row.cast_shadow;
      light.shadow.mapSize.set(row.shadow_map, row.shadow_map);
      light.shadow.camera.near = row.shadow_near; light.shadow.camera.far = row.shadow_far;
      light.shadow.bias = -0.00002; light.shadow.normalBias = row.normal_bias;
      light.shadow.camera.updateProjectionMatrix();
    }
    setGroup(group);
    shipRoot.traverse(o => { if (o.isMesh) { meshes.push([o, o.castShadow, o.receiveShadow]); o.castShadow = true; o.receiveShadow = true; } });
    shipRoot.add(gltf.scene); attached = true;
    signal?.addEventListener('abort', dispose, { once: true });
    return { root: gltf.scene, setGroup, requiresShadowMap: true, dispose };
  } catch (error) { dispose(); throw error; }
}
