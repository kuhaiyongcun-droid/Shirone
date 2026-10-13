/** Attach the verified light-only GLB after the main ship is loaded.
 * The caller supplies its existing THREE-compatible GLTFLoader, ship root,
 * profile JSON and exact model SHA. No renderer, camera, RAF or pointer changes.
 * Call dispose() before replacing the ship or leaving the homepage.
 * Browser integration and shadow tuning are still pending actual QA.
 */
const owners = new WeakMap();

export async function attachServiceLighting({ loader, shipRoot, profile, modelSha256, lightUrl, intensityScale, signal }) {
  if (!loader?.loadAsync || !shipRoot?.add || !shipRoot?.traverse) {
    throw new Error('An existing GLTFLoader and ship root are required');
  }
  if (profile?.revision !== 'side-lighting-07' || profile.model_sha256 !== modelSha256) {
    throw new Error('Lighting profile does not match the loaded ship revision');
  }
  if (!Number.isFinite(intensityScale) || intensityScale <= 0) {
    throw new Error('Calibrate intensityScale against the host scene before attaching photometric lights');
  }
  if (owners.has(shipRoot)) throw new Error('Dispose the existing service lighting first');
  if (signal?.aborted) throw new Error('Service lighting attachment cancelled');
  const reservation = {};
  owners.set(shipRoot, reservation);
  let gltf;
  try {
    gltf = await loader.loadAsync(lightUrl);
    if (signal?.aborted) throw new Error('Service lighting attachment cancelled');
    const settings = new Map(profile.lights.map(row => [row.id, row]));
    const lights = [];
    gltf.scene.traverse(object => { if (object.isLight) lights.push(object); });
    if (lights.length !== 3 || lights.some(light => !settings.has(light.userData.service_light_id))) {
      throw new Error('Unexpected service light asset');
    }
    for (const light of lights) {
      const row = settings.get(light.userData.service_light_id);
      light.intensity *= intensityScale;
      light.castShadow = row.cast_shadow;
      light.shadow.mapSize.set(row.shadow_map, row.shadow_map);
      light.shadow.camera.near = row.shadow_near;
      light.shadow.camera.far = row.shadow_far;
      light.shadow.bias = -0.00002;
      light.shadow.normalBias = 0.0003;
      light.shadow.camera.updateProjectionMatrix();
    }
    const meshes = [];
    shipRoot.traverse(object => {
      if (object.isMesh) {
        meshes.push([object, object.castShadow, object.receiveShadow]);
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
    shipRoot.add(gltf.scene);
    let disposed = false;
    function dispose() {
        if (disposed) return;
        disposed = true;
        shipRoot.remove(gltf.scene);
        for (const light of lights) light.shadow?.dispose?.();
        for (const [mesh, cast, receive] of meshes) {
          mesh.castShadow = cast;
          mesh.receiveShadow = receive;
        }
        owners.delete(shipRoot);
        signal?.removeEventListener('abort', dispose);
    }
    signal?.addEventListener('abort', dispose, { once: true });
    return { root: gltf.scene, requiresShadowMap: true, dispose };
  } catch (error) {
    gltf?.scene?.traverse(object => { if (object.isLight) object.shadow?.dispose?.(); });
    owners.delete(shipRoot);
    throw error;
  }
}
