import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { cutawayOpen, renderScale } from './interaction.mjs';
import { makeSpace } from './space.mjs';
import { fitShip, overviewTarget } from './framing.mjs';

const anchor = new THREE.Vector3(-.80, .30, .48);
const archiveTarget = new THREE.Vector3(-.80, .20, .37);

export async function createViewer({ viewport, hotspot, quality, state, onError, onLoading, signal }) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070b0f);
  const camera = new THREE.PerspectiveCamera(38, 1, .015, 400);
  const renderer = new THREE.WebGLRenderer({ antialias: quality !== 'light', powerPreference: 'default' });
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = quality !== 'light';
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  renderer.domElement.hidden = true;
  viewport.prepend(renderer.domElement);
  const controls = new OrbitControls(camera, viewport);
  controls.enablePan = false;
  controls.enableDamping = false;
  controls.autoRotate = false;
  controls.rotateSpeed = .65;
  controls.minPolarAngle = .06; controls.maxPolarAngle = Math.PI - .06;
  controls.minDistance = 3.6; controls.maxDistance = 20;
  const abort = new AbortController();
  const draco = new DRACOLoader();
  draco.setDecoderPath(new URL('./assets/draco/', document.baseURI).href);
  draco.setDecoderConfig({ type: 'wasm' });
  draco.setWorkerLimit(2);
  const loader = new GLTFLoader().setDRACOLoader(draco);
  let dead = false, raf = 0, ready = false, currentMode = 'ship';
  let interior = null, interiorPromise = null, savedView = null;
  let ship = null, shipBounds = null;
  const hull = [], shell = [];
  const outline = new THREE.Group(); outline.visible = false; scene.add(outline);
  const space = makeSpace(); scene.add(space);
  const pointer = new THREE.Vector2(), ray = new THREE.Raycaster();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = new RoomEnvironment();
  const environmentTarget = pmrem.fromScene(environment, .06);
  scene.environment = environmentTarget.texture;
  scene.environmentIntensity = .32;
  environment.dispose(); pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xa8c6d6, 0x192426, .55));
  const sun = new THREE.DirectionalLight(new THREE.Color(1, .8, .6), 4.5);
  sun.position.set(1.2, 4.9, -8.6);
  sun.castShadow = quality !== 'light';
  sun.shadow.mapSize.set(768, 768);
  Object.assign(sun.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4, near: .1, far: 24 });
  sun.shadow.bias = -.0003; sun.shadow.normalBias = .003;
  scene.add(sun);
  const rim = new THREE.DirectionalLight(new THREE.Color(.3, .48, .7), 1.1);
  rim.position.set(-4.8, 3.1, 6.2); scene.add(rim);
  const archiveLight = new THREE.PointLight(0xffc789, .15, .6, 2);
  archiveLight.position.set(-.81, .32, .35); archiveLight.visible = false; scene.add(archiveLight);

  function request() { if (!dead && !document.hidden && !raf) raf = requestAnimationFrame(render); }
  function projectBeacon() {
    if (!ready || state().mode !== 'ship') { hotspot.hidden = true; return; }
    scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
    const p = anchor.clone().project(camera);
    const w = viewport.clientWidth, h = viewport.clientHeight;
    const x = (p.x + 1) * w / 2, y = (1 - p.y) * h / 2;
    ray.set(camera.position, anchor.clone().sub(camera.position).normalize());
    const obstacle = ray.intersectObjects(hull, false)[0];
    const obscured = obstacle && obstacle.distance < camera.position.distanceTo(anchor) - .035;
    hotspot.hidden = p.z < -1 || p.z > 1 || x < 25 || x > w - 25 || y < 115 || y > h - 150 || !!obscured;
    if (!hotspot.hidden) { hotspot.style.left = `${x}px`; hotspot.style.top = `${y}px`; }
  }
  function render() {
    raf = 0;
    if (dead || document.hidden) return;
    projectBeacon();
    renderer.render(scene, camera);
  }
  function fitOverview() {
    controls.target.copy(overviewTarget);
    const distance = fitShip(camera, shipBounds);
    controls.maxDistance = Math.max(20, distance * 1.5);
    controls.update(); request();
  }
  function resize() {
    const w = Math.max(1, viewport.clientWidth), h = Math.max(1, viewport.clientHeight);
    const previousAspect = camera.aspect;
    camera.aspect = w / h; camera.updateProjectionMatrix();
    renderer.setPixelRatio(renderScale(w, h, devicePixelRatio || 1, quality));
    renderer.setSize(w, h, false);
    // A device rotation may need a wider framing. Hover never calls this path.
    if (ready && currentMode === 'ship' && (previousAspect < 1) !== (camera.aspect < 1)) fitOverview();
    request();
  }
  const observer = new ResizeObserver(resize); observer.observe(viewport);
  controls.addEventListener('change', request);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else request();
  }, { signal: abort.signal });
  renderer.domElement.addEventListener('webglcontextlost', (event) => {
    event.preventDefault(); if (!dead) onError();
  }, { signal: abort.signal });

  async function loadModel(name) {
    const controller = new AbortController();
    const stop = () => controller.abort();
    abort.signal.addEventListener('abort', stop, { once: true });
    let timer;
    try {
      return await Promise.race([
        (async () => {
          const url = new URL(`./assets/${name}`, document.baseURI);
          url.searchParams.set('v', 'review-study-02');
          const response = await fetch(url, { signal: controller.signal });
          if (!response.ok) throw Error(`Model HTTP ${response.status}`);
          const data = await loader.parseAsync(await response.arrayBuffer(), '');
          if (dead) { disposeObject(data.scene); throw Error('Viewer disposed'); }
          return data.scene;
        })(),
        new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(Error('Model load timed out')); }, 30000); })
      ]);
    } finally { clearTimeout(timer); abort.signal.removeEventListener('abort', stop); }
  }
  function prepare(object) {
    object.traverse((mesh) => {
      if (!mesh.isMesh) return;
      mesh.castShadow = true; mesh.receiveShadow = true;
      mesh.geometry.computeBoundingSphere();
    });
  }
  function loadInterior() {
    if (interiorPromise) return interiorPromise;
    onLoading(true);
    interiorPromise = loadModel('archive.glb').then((object) => {
      interior = object; prepare(interior); scene.add(interior);
      update(state()); onLoading(false); return interior;
    }).catch((error) => { if (!dead) { console.warn(error); onError(); } });
    return interiorPromise;
  }
  function applyCutaway(value) {
    // Same shell geometry remains raycastable when hidden. No spatial proxy or
    // bounding box pretends to be the compartment. Surface occlusion uses hull.
    for (const mesh of shell) mesh.visible = !value;
    outline.visible = value && currentMode === 'ship';
    if (interior) interior.visible = value;
    archiveLight.visible = value;
  }
  function update(next) {
    if (dead || !ready) return;
    const room = next.mode === 'archive';
    if (next.mode !== currentMode) {
      if (room) {
        savedView = { position: camera.position.clone(), target: controls.target.clone(), maxDistance: controls.maxDistance };
        controls.minDistance = .35; controls.maxDistance = 2;
        controls.target.copy(archiveTarget);
        const distance = camera.aspect < .85 ? 1.35 : .92;
        camera.position.copy(archiveTarget).addScaledVector(new THREE.Vector3(-.68, .69, .89).normalize(), distance);
      } else {
        controls.minDistance = 3.6; controls.maxDistance = savedView?.maxDistance || 20;
        if (savedView) { camera.position.copy(savedView.position); controls.target.copy(savedView.target); }
        else fitOverview();
      }
      currentMode = next.mode;
      for (const mesh of hull) mesh.visible = !room;
      space.visible = !room;
      controls.update();
    }
    const open = cutawayOpen(next);
    if (open && !interiorPromise) loadInterior();
    // Don't remove the hull cover until the real interior has loaded.
    applyCutaway(open && !!interior);
    if (room) for (const mesh of shell) mesh.visible = false;
    request();
  }
  function hit(clientX, clientY) {
    if (!ready || currentMode !== 'ship') return false;
    const rect = viewport.getBoundingClientRect();
    pointer.set((clientX - rect.left) / rect.width * 2 - 1, -(clientY - rect.top) / rect.height * 2 + 1);
    scene.updateMatrixWorld(true); camera.updateMatrixWorld(true); ray.setFromCamera(pointer, camera);
    // Raycaster does not filter .visible: keep hidden cover pickable while open.
    const first = ray.intersectObjects([...hull, ...shell], false)[0];
    return !!first && shell.includes(first.object);
  }
  function reset() {
    if (currentMode === 'archive') {
      controls.target.copy(archiveTarget); camera.position.copy(archiveTarget).add(new THREE.Vector3(-.55, .55, .72));
      controls.update(); request();
    } else fitOverview();
  }
  function key(keyName) {
    const delta = .10;
    const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
    if (keyName === 'ArrowLeft') spherical.theta += delta;
    else if (keyName === 'ArrowRight') spherical.theta -= delta;
    else if (keyName === 'ArrowUp') spherical.phi -= delta;
    else if (keyName === 'ArrowDown') spherical.phi += delta;
    else if (['+', '='].includes(keyName)) spherical.radius *= .90;
    else if (['-', '−'].includes(keyName)) spherical.radius /= .90;
    else return false;
    spherical.phi = THREE.MathUtils.clamp(spherical.phi, .06, Math.PI - .06);
    spherical.radius = THREE.MathUtils.clamp(spherical.radius, controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update(); request(); return true;
  }
  function disposeObject(root) {
    const geometries = new Set(), materials = new Set();
    root.traverse((item) => {
      if (item.geometry) geometries.add(item.geometry);
      if (item.material) for (const m of (Array.isArray(item.material) ? item.material : [item.material])) materials.add(m);
    });
    for (const g of geometries) g.dispose();
    for (const m of materials) m.dispose();
  }
  function dispose() {
    if (dead) return;
    dead = true; abort.abort(); observer.disconnect(); cancelAnimationFrame(raf);
    signal?.removeEventListener('abort', dispose);
    controls.dispose(); draco.dispose(); disposeObject(scene); environmentTarget.dispose();
    sun.shadow.map?.dispose(); renderer.dispose(); renderer.domElement.remove();
  }
  try {
    if (signal?.aborted) throw Error('Viewer disposed');
    signal?.addEventListener('abort', dispose, { once: true });
    resize(); ship = await loadModel('flagship.glb');
    prepare(ship); scene.add(ship); scene.updateMatrixWorld(true);
    shipBounds = new THREE.Box3().setFromObject(ship);
    ship.traverse((mesh) => {
      if (!mesh.isMesh) return;
      if (mesh.userData.role === 'archive_shell') {
        shell.push(mesh);
        const line = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 24), new THREE.LineBasicMaterial({ color: 0xe8b775, transparent: true, opacity: .9 }));
        line.matrixAutoUpdate = false; line.matrix.copy(mesh.matrixWorld); outline.add(line);
      } else hull.push(mesh);
    });
    if (!shell.length || !hull.length) throw Error('Missing semantic model groups');
    ready = true; renderer.domElement.hidden = false; fitOverview(); update(state());
    return { update, hit, reset, key, dispose, locate: fitOverview };
  } catch (error) { dispose(); throw error; }
}
