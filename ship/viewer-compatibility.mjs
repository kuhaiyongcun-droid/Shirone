import { lightAppliesToView } from './src/runtime-guards.mjs';

// The published UI and lighting acceptance matrix depend on these exact IDs.
// Adding/removing a view is an interface revision, never an alias or silent remap.
export const REQUIRED_VIEWS = Object.freeze([
  ['whole-ship', 'exterior', 'ORTHO'], ['whole-underside', 'exterior', 'ORTHO'],
  ['archive-locator', 'exterior', 'PERSP'], ['archive-cutaway', 'archive', 'PERSP'],
  ['archive-entry', 'archive', 'PERSP'], ['archive-upper', 'archive', 'PERSP'],
  ['vestibule', 'archive', 'PERSP'],
]);
export function assertViewerCompatibility(runtime) {
  const { cameras, lighting, references } = runtime;
  const missing = REQUIRED_VIEWS.filter(([id]) => !cameras.views.some(v => v.id === id)).map(([id]) => id);
  if (missing.length) throw Error('Viewer interface missing views: ' + missing.join(', '));
  if (cameras.views.length !== REQUIRED_VIEWS.length) throw Error('Viewer interface requires exactly seven reviewed views');
  for (const [id, scope, projection] of REQUIRED_VIEWS) {
    const view = cameras.views.find(v => v.id === id);
    if (view.scope !== scope || view.projection !== projection) throw Error('Viewer scope/projection differs: ' + id);
    for (const mode of ['neutral', 'space']) if (!lighting.lights.some(light => light.intensity_web > 0 && lightAppliesToView(light, { scope, view: id, mode })))
      throw Error('No applicable nonzero lighting recipe: ' + id + '/' + mode);
  }
  if (cameras.defaults.exterior !== 'whole-ship' || cameras.defaults.archive !== 'archive-cutaway' || cameras.archive_locator_view !== 'archive-locator')
    throw Error('Viewer defaults/locator differ from the published interface');
  const [width, height] = cameras.reference_resolution;
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width / height !== 8 / 5) throw Error('Viewer reference frame must be integer 8:5');
  for (const ref of references.frames) if (JSON.stringify(ref.resolution) !== JSON.stringify(cameras.reference_resolution))
    throw Error('Reference resolution differs from the camera frame: ' + ref.view_id + '/' + ref.light);
  return { interface: 'ship-seven-views-v1', views: REQUIRED_VIEWS.length, referenceFrames: references.frames.length, resolution: [width, height] };
}

export function assertReferencePng(bytes, expectedResolution) {
  const data = Buffer.from(bytes);
  if (data.length < 33 || !data.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) || data.toString('ascii', 12, 16) !== 'IHDR')
    throw Error('Published reference must be an actual PNG with IHDR');
  if (data.readUInt32BE(16) !== expectedResolution[0] || data.readUInt32BE(20) !== expectedResolution[1])
    throw Error('PNG dimensions differ from the reference declaration');
}
