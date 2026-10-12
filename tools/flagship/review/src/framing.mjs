import * as THREE from 'three';

// home-look-01's fixed starting direction, converted from Blender Z-up.
export const overviewTarget = new THREE.Vector3(.12, .12, 0);
const overviewDirection = new THREE.Vector3(-5.77, 3.18, 7.15).normalize();

export function fitShip(camera, box) {
  const corners = [];
  for (const x of [box.min.x, box.max.x])
    for (const y of [box.min.y, box.max.y])
      for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
  function place(distance) {
    camera.position.copy(overviewTarget).addScaledVector(overviewDirection, distance);
    camera.lookAt(overviewTarget); camera.updateMatrixWorld(true);
    return corners.every(corner => {
      const p = corner.clone().project(camera);
      return p.x >= -.82 && p.x <= .82 && p.y >= -.57 && p.y <= .65 && p.z > -1 && p.z < 1;
    });
  }
  let low = 3.6, high = 20;
  while (!place(high) && high < 200) high *= 1.5;
  for (let i = 0; i < 24; i++) {
    const middle = (low + high) / 2;
    if (place(middle)) high = middle; else low = middle;
  }
  place(high);
  return high;
}
