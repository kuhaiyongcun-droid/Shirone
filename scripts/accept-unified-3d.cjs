// Real Firefox / localhost stream acceptance. No live-server or physical-phone claim.
// node accept-unified-3d.cjs --dist=... --output=... --firefox=... --playwright=... [--case=desktop|http|decoder|mobile]
'use strict';
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { setTimeout: delay } = require('node:timers/promises');
const args = {};
for (const value of process.argv.slice(2)) {
  const m = /^--(dist|output|firefox|playwright|case)=(.+)$/.exec(value);
  if (!m || args[m[1]]) throw Error('Expected unique --dist, --output, --firefox, --playwright and optional --case');
  args[m[1]] = m[2];
}
for (const key of ['dist', 'output', 'firefox', 'playwright']) if (!args[key]) throw Error(`Missing --${key}`);
const requestedCase = args.case || 'all', caseNames = ['desktop', 'http', 'decoder', 'mobile'];
if (requestedCase !== 'all' && !caseNames.includes(requestedCase)) throw Error('Invalid --case');
const selectedCases = requestedCase === 'all' ? caseNames : [requestedCase];
const dist = fs.realpathSync(args.dist), output = path.resolve(args.output), rate = 360000;
const relativeOutput = path.relative(dist, output);
if (!relativeOutput.startsWith('..' + path.sep) && relativeOutput !== '..' && !path.isAbsolute(relativeOutput)) throw Error('Evidence must be outside dist');
const contract = JSON.parse(fs.readFileSync(path.join(dist, 'assets/p23-asset-contract.json'), 'utf8'));
const assetPaths = Object.fromEntries(Object.entries(contract.assets).map(([key, asset]) => [key, new URL(asset.uri, 'http://localhost/').pathname]));
const totalBytes = Object.values(contract.assets).reduce((sum, asset) => sum + asset.bytes, 0);
const assetInspection = {};
for (const [key, asset] of Object.entries(contract.assets)) {
  const buffer = fs.readFileSync(path.join(dist, '.' + assetPaths[key]));
  assert.equal(buffer.length, asset.bytes, `${key} pinned length`);
  assert.equal(crypto.createHash('sha256').update(buffer).digest('hex'), asset.sha256, `${key} pinned SHA256`);
  const json = JSON.parse(buffer.subarray(20, 20 + buffer.readUInt32LE(12)).toString('utf8'));
  assetInspection[key] = { extensionsUsed: json.extensionsUsed || [], extensionsRequired: json.extensionsRequired || [],
    dracoPrimitiveCount: (json.meshes || []).flatMap(mesh => mesh.primitives || []).filter(primitive => primitive.extensions?.KHR_draco_mesh_compression).length };
}
fs.mkdirSync(path.dirname(output), { recursive: true }); fs.mkdirSync(output);
const { firefox } = require(path.resolve(args.playwright));
const report = { schema: 'unified-scene-browser-acceptance-v1', started: new Date().toISOString(), dist,
  scope: 'Assembled local distribution with real streamed GLB responses and existing Firefox headless. Not a public deployment, physical mobile device, or native Codex browser acceptance.',
  engine: path.resolve(args.firefox), selectedCases, ratePerModelBytesPerSecond: rate, totalBytes,
  modelPins: contract.assets, assetInspection, source: contract.source_scene,
  memoryLimit: 'renderer.info.memory counts GPU resources; it is not VRAM bytes. Firefox does not provide performance.memory; process-wide OS memory and GPU-byte profiling are not measured.',
  requests: [], responses: [], failures: [], serverRequests: [], console: [], pageErrors: [], workers: [], stages: [], cases: [], assertions: [], timelines: {}, lifecycle: {},
};
let policy = { mode: 'fast', scenario: 'startup' }, browser, server, base;
const sockets = new Set();
const checkpoint = () => fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2) + '\n');
function check(name, condition, detail) {
  report.assertions.push({ name, pass: !!condition, detail }); checkpoint(); assert.ok(condition, name + (detail ? ': ' + JSON.stringify(detail) : ''));
}
async function until(predicate, timeout = 10000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { const result = predicate(); if (result) return result; await delay(50); }
  throw Error('Timed out waiting for server evidence');
}
const mime = file => ({ '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2' })[path.extname(file)] || 'application/octet-stream';
async function serve(req, res) {
  const started = Date.now(), selected = { ...policy };
  const row = { id: report.serverRequests.length + 1, url: req.url, startedMs: started, scenario: selected.scenario, mode: selected.mode, bytesSent: 0 };
  report.serverRequests.push(row); let stream;
  res.on('close', () => { Object.assign(row, { closed: true, completed: res.writableFinished, endedMs: Date.now(), durationMs: Date.now() - started, endReason: res.writableFinished ? 'complete' : 'client-aborted' }); stream?.destroy(); });
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1/').pathname);
    let file = path.resolve(dist, '.' + pathname), relative = path.relative(dist, file);
    if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('Outside dist');
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    file = fs.realpathSync(file); relative = path.relative(dist, file);
    if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('Outside dist');
    const stat = fs.statSync(file), isModel = path.extname(file) === '.glb';
    Object.assign(row, { path: pathname, fileBytes: stat.size, scope: Object.keys(assetPaths).find(key => assetPaths[key] === pathname) || null,
      decoderAsset: /\/assets\/draco\/[^/]+\.(?:js|wasm)$/.test(pathname) });
    if (row.decoderAsset && selected.mode === 'decoder-delay') {
      // Real FileLoader network requests remain pending while the user cancels.
      // This exercises a decoder initialization race rather than a GLB fetch abort.
      await delay(6000); if (res.destroyed) return;
    }
    if (isModel && selected.mode === 'archive-error' && row.scope === 'archive') {
      await delay(1500); if (res.destroyed) return;
      row.status = 503; res.writeHead(503, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }); res.end('Controlled archive HTTP 503'); return;
    }
    row.status = 200; res.writeHead(200, { 'Content-Type': mime(file), 'Content-Length': stat.size, 'Cache-Control': 'no-store' });
    if (req.method === 'HEAD') { res.end(); return; }
    const slow = isModel && ['slow', 'archive-error'].includes(selected.mode);
    stream = fs.createReadStream(file, { highWaterMark: slow ? rate / 10 : 256 * 1024 });
    for await (const chunk of stream) {
      if (slow) await delay(chunk.length / rate * 1000);
      if (res.destroyed) break;
      const writable = res.write(chunk); row.bytesSent += chunk.length;
      if (!writable) await new Promise(resolve => {
        const resume = () => { res.off('drain', resume); res.off('close', resume); resolve(); };
        res.once('drain', resume); res.once('close', resume);
      });
    }
    if (!res.destroyed) res.end();
  } catch (error) {
    if (res.destroyed) return; row.error = String(error);
    if (!res.headersSent) { row.status = 404; res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('Not found'); }
    else res.destroy(error);
  }
}
function instrument(page, name) {
  page.on('request', request => report.requests.push({ case: name, at: Date.now(), url: request.url(), type: request.resourceType() }));
  page.on('response', response => report.responses.push({ case: name, at: Date.now(), url: response.url(), status: response.status() }));
  page.on('requestfailed', request => report.failures.push({ case: name, at: Date.now(), url: request.url(), failure: request.failure() }));
  page.on('pageerror', error => report.pageErrors.push({ case: name, error: String(error.stack || error) }));
  page.on('console', message => report.console.push({ case: name, type: message.type(), text: message.text(), location: message.location() }));
  page.on('worker', worker => {
    const row = { case: name, url: worker.url(), created: Date.now() }; report.workers.push(row);
    worker.on('close', () => { row.closed = Date.now(); });
  });
}
async function state(page) {
  return page.evaluate(() => ({ url: location.href, language: document.documentElement.lang, ready: document.body.dataset.ready,
    status: document.getElementById('status')?.textContent, activeElement: document.activeElement?.id,
    posterVisible: !!document.getElementById('poster') && !document.getElementById('poster').hidden,
    canvas: document.querySelectorAll('#viewport canvas').length,
    visibleCanvas: [...document.querySelectorAll('#viewport canvas')].filter(canvas => !canvas.hidden).length,
    busy: document.getElementById('viewport')?.getAttribute('aria-busy'),
    enableVisible: !!document.getElementById('enable-3d') && !document.getElementById('enable-3d').hidden,
    disableVisible: !!document.getElementById('disable-3d') && !document.getElementById('disable-3d').hidden,
    enableText: document.getElementById('enable-3d')?.textContent, maxTouchPoints: navigator.maxTouchPoints,
    coarsePointer: matchMedia('(pointer: coarse)').matches,
    pointerEvents: window.__unifiedAcceptance?.pointers || [], lifecycle: window.__unifiedAcceptance?.lifecycle || [],
    jsMemory: performance.memory ? { ...performance.memory } : null, snapshot: window.__flagshipReview?.snapshot(),
  }));
}
async function stage(page, name, screenshot = true) {
  const value = await state(page); report.stages.push({ stage: name, at: Date.now(), state: value });
  if (screenshot) await page.screenshot({ path: path.join(output, name + '.png'), fullPage: false });
  checkpoint(); console.log(JSON.stringify({ stage: name, ready: value.ready, status: value.status, progress: value.snapshot?.loadProgress, memory: value.snapshot?.memory })); return value;
}
async function fresh(name, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', ...options });
  await context.addInitScript(() => {
    const data = window.__unifiedAcceptance = { samples: [], lifecycle: [], pointers: [] };
    const seen = new WeakSet(); let sequence = 0;
    new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) {
        const canvases = node instanceof HTMLCanvasElement ? [node] : node.querySelectorAll?.('canvas') || [];
        for (const canvas of canvases) if (!seen.has(canvas)) {
          seen.add(canvas); const id = ++sequence; data.lifecycle.push({ type: 'canvas-added', id, at: Date.now() });
          canvas.addEventListener('webglcontextlost', () => data.lifecycle.push({ type: 'webglcontextlost', id, at: Date.now(), connected: canvas.isConnected }));
        }
      }
      for (const record of records) for (const node of record.removedNodes) if (node instanceof HTMLCanvasElement) data.lifecycle.push({ type: 'canvas-removed', at: Date.now() });
    }).observe(document, { childList: true, subtree: true });
    document.addEventListener('pointerdown', event => data.pointers.push({ pointerType: event.pointerType, isTrusted: event.isTrusted, target: event.target.closest?.('button')?.id || event.target.id, at: Date.now() }), { capture: true });
    setInterval(() => {
      const snapshot = window.__flagshipReview?.snapshot(); if (!snapshot) return;
      data.samples.push({ at: Date.now(), ready: document.body.dataset.ready, loadProgress: snapshot.loadProgress,
        interiorLoaded: snapshot.interiorLoaded, sceneAssetsReady: snapshot.sceneAssetsReady, visibleCanvas: [...document.querySelectorAll('#viewport canvas')].filter(canvas => !canvas.hidden).length });
    }, 250);
  });
  const page = await context.newPage(); page.setDefaultTimeout(20000); instrument(page, name);
  await page.goto(base + '/?qa=1', { waitUntil: 'networkidle' }); return { context, page };
}
async function captureTelemetry(page, key) {
  if (page.isClosed()) return;
  const data = await page.evaluate(() => window.__unifiedAcceptance || null).catch(() => null);
  if (data) { report.timelines[key] = data.samples; report.lifecycle[key] = data.lifecycle; checkpoint(); }
}
async function waitDownloadingBoth(page) {
  await page.waitForFunction(() => {
    const p = window.__flagshipReview?.snapshot().loadProgress;
    return p?.scope === 'scene' && p.phase === 'downloading' && p.assets?.length === 2 && p.assets.every(asset => asset.loaded > 0 && asset.loaded < asset.total);
  }, null, { timeout: 45000 });
}
async function interactive(page) {
  await page.waitForFunction(() => ['interactive', 'fallback'].includes(document.body.dataset.ready), null, { timeout: 180000 });
  const value = await state(page); assert.equal(value.ready, 'interactive', 'Unexpected fallback');
  assert.equal(value.snapshot.sceneAssetsReady, true); assert.equal(value.snapshot.interiorLoaded, true); assert.equal(value.snapshot.interiorLoading, false);
  await delay(250); return value;
}
const modelRows = scenario => report.serverRequests.filter(row => row.scope && (!scenario || row.scenario === scenario));
const modelCount = () => modelRows().length;
const matrixEqual = (a, b, tolerance = 1e-8) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((value, i) => Math.abs(value - b[i]) <= tolerance);
async function enter(page, touch = false) {
  for (let count = 0; count < 2; count++) {
    if ((await state(page)).snapshot.state.mode === 'archive') break;
    await page.locator('#enter')[touch ? 'tap' : 'click']();
  }
  await page.waitForFunction(() => window.__flagshipReview?.snapshot().state.mode === 'archive'); await delay(250);
}
async function stopAndAssert(page, name, rows = [], touch = false) {
  // The real settings panel overlays the journey controls. Close it through
  // its normal control before interacting with the page underneath it.
  if (await page.locator('#settings').isVisible()) await page.locator('#settings-close')[touch ? 'tap' : 'click']();
  await page.locator('#disable-3d')[touch ? 'tap' : 'click']();
  await page.waitForFunction(() => document.body.dataset.ready === 'static' && document.querySelectorAll('#viewport canvas').length === 0);
  await until(() => rows.every(row => row.closed)); await delay(300);
  const value = await stage(page, name);
  check(name + '-requests-aborted', rows.every(row => !row.completed && row.bytesSent < row.fileBytes), rows);
  check(name + '-clean-static-focus', value.canvas === 0 && value.posterVisible && value.enableVisible && !value.disableVisible && !value.snapshot.loadProgress && !value.snapshot.failureCode && value.activeElement === 'enable-3d', value);
  await page.waitForFunction(() => window.__unifiedAcceptance.lifecycle.filter(row => row.type === 'canvas-added').length === window.__unifiedAcceptance.lifecycle.filter(row => row.type === 'webglcontextlost').length);
  check(name + '-webgl-contexts-released', true, (await state(page)).lifecycle);
  await until(() => page.workers().length === 0);
  check(name + '-decoder-workers-closed', page.workers().length === 0);
  return value;
}
async function runCase(name, body) {
  if (!selectedCases.includes(name)) return;
  const row = { name, started: new Date().toISOString() }; report.cases.push(row);
  try {
    const result = await body();
    if (result?.result === 'NOT_APPLICABLE_CURRENT_ASSETS') Object.assign(row, result);
    else row.result = 'PASS';
  }
  catch (error) { row.result = 'FAIL'; row.error = String(error.stack || error); process.exitCode = 1; }
  finally { row.finished = new Date().toISOString(); checkpoint(); console.log(JSON.stringify(row)); }
}
(async () => {
  try {
    server = http.createServer((req, res) => { void serve(req, res); });
    server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    base = 'http://127.0.0.1:' + server.address().port; report.base = base;
    browser = await firefox.launch({ headless: true, executablePath: path.resolve(args.firefox) }); report.browserVersion = browser.version();
    await runCase('desktop', async () => {
      policy = { mode: 'slow', scenario: 'desktop-unified-slow' };
      const { context, page } = await fresh('desktop');
      try {
        const initial = await stage(page, 'desktop-static');
        check('desktop-default-no-3d-download', initial.ready === 'static' && initial.canvas === 0 && modelCount() === 0);
        const clicked = Date.now(); await page.locator('#enable-3d').click(); await waitDownloadingBoth(page);
        const both = await stage(page, 'desktop-both-assets-downloading');
        check('one-progress-total-for-both-assets', both.snapshot.loadProgress.total === totalBytes && both.snapshot.loadProgress.loaded === both.snapshot.loadProgress.assets.reduce((sum, item) => sum + item.loaded, 0), both.snapshot.loadProgress);
        const active = modelRows('desktop-unified-slow');
        check('initial-download-starts-both-models-concurrently', active.length === 2 && Math.abs(active[0].startedMs - active[1].startedMs) < 2000, active);
        await delay(Math.max(0, 32000 - (Date.now() - clicked)));
        const later = await stage(page, 'desktop-progress-after-32s');
        check('never-interactive-while-any-model-loading', later.ready === 'loading' && later.visibleCanvas === 0 && later.posterVisible && later.snapshot.loadProgress.scope === 'scene' && later.snapshot.loadProgress.total === totalBytes, later);
        await page.locator('#language').click();
        const english = await stage(page, 'desktop-total-progress-english');
        check('english-total-progress', english.language === 'en' && /Downloading/.test(english.status) && /%/.test(english.status), english.status);
        await page.locator('#language').click(); await interactive(page);
        const complete = await stage(page, 'desktop-both-assets-ready');
        check('both-models-complete-before-first-interactive', active.every(row => row.completed && row.bytesSent === contract.assets[row.scope].bytes) && complete.snapshot.sceneAssetsReady && complete.snapshot.interiorLoaded && !complete.snapshot.loadProgress, active);
        check('slow-exterior-exceeds-60-seconds', active.find(row => row.scope === 'exterior').durationMs > 60000, active);
        check('model-hashes-and-provenance-preserved', complete.snapshot.modelSha256 === contract.assets.exterior.sha256 && complete.snapshot.archiveSha256 === contract.assets.archive.sha256 && complete.snapshot.browserAcceptance === false && complete.snapshot.lightingCalibrated === false, complete.snapshot);
        const telemetry = await page.evaluate(() => window.__unifiedAcceptance.samples);
        const progressing = telemetry.filter(item => item.loadProgress);
        check('total-progress-monotonic-and-constant-size', progressing.length > 20 && progressing.every((item, i) => item.loadProgress.scope === 'scene' && item.loadProgress.total === totalBytes && (!i || item.loadProgress.loaded >= progressing[i - 1].loadProgress.loaded)), progressing.map(item => ({ at: item.at, ready: item.ready, progress: item.loadProgress })));
        check('timeline-has-no-premature-interactive', telemetry.filter(item => item.ready === 'interactive').every(item => item.sceneAssetsReady && item.interiorLoaded));
        const beforeSwitches = modelCount();
        await page.locator('#enter').click(); // Locate and select the archive; no file request.
        await page.keyboard.press('Escape');
        await page.locator('#hotspot').waitFor({ state: 'visible' });
        const beforeHover = await state(page);
        await page.locator('#hotspot').hover(); await delay(300);
        const hovered = await stage(page, 'desktop-hover-resident-archive');
        check('hover-opens-resident-archive-without-camera-transform', hovered.snapshot.state.hover && hovered.snapshot.interiorLoaded && matrixEqual(beforeHover.snapshot.cameraWorldMatrix, hovered.snapshot.cameraWorldMatrix) && matrixEqual(beforeHover.snapshot.shipMatrix, hovered.snapshot.shipMatrix), { before: beforeHover.snapshot.cameraWorldMatrix, after: hovered.snapshot.cameraWorldMatrix });
        await page.locator('#home').hover(); await delay(200);
        const cycleMemory = [];
        for (let cycle = 0; cycle < 3; cycle++) {
          if (!(await state(page)).snapshot.state.selected) await page.locator('#enter').click();
          const before = await state(page);
          await enter(page); const archive = await stage(page, `desktop-archive-cycle-${cycle}`, cycle === 0);
          check(`archive-cycle-${cycle}-already-resident`, archive.snapshot.interiorLoaded && !archive.snapshot.interiorLoading && !archive.snapshot.loadProgress && archive.ready === 'interactive');
          await page.locator('#back').click(); await delay(250); const back = await state(page);
          check(`archive-cycle-${cycle}-restores-camera-keeps-assets`, matrixEqual(before.snapshot.cameraWorldMatrix, back.snapshot.cameraWorldMatrix) && back.snapshot.interiorLoaded && !back.snapshot.loadProgress && back.activeElement === 'enter', { before: before.snapshot.cameraWorldMatrix, back: back.snapshot.cameraWorldMatrix, memory: back.snapshot.memory });
          cycleMemory.push(back.snapshot.memory);
        }
        check('hover-entry-return-never-request-models-again', modelCount() === beforeSwitches, { beforeSwitches, afterSwitches: modelCount() });
        check('resident-resource-count-stable-after-warmup', cycleMemory.every(value => value.geometries === cycleMemory[0].geometries && value.textures === cycleMemory[0].textures), cycleMemory);
        // A quality rebuild is an explicit new initialization, unlike a view change.
        await enter(page); const qualityBefore = await state(page);
        policy = { mode: 'fast', scenario: 'desktop-quality-rebuild' };
        await page.locator('#settings-toggle').click(); await page.locator('#quality').selectOption('light'); await interactive(page);
        const qualityAfter = await stage(page, 'desktop-light-quality-rebuild');
        check('quality-rebuild-initializes-both-models', modelRows('desktop-quality-rebuild').length === 2 && qualityAfter.snapshot.sceneAssetsReady && qualityAfter.snapshot.quality === 'light', modelRows('desktop-quality-rebuild'));
        check('quality-rebuild-restores-archive-camera', qualityAfter.snapshot.state.mode === 'archive' && matrixEqual(qualityBefore.snapshot.cameraWorldMatrix, qualityAfter.snapshot.cameraWorldMatrix), { before: qualityBefore.snapshot.cameraWorldMatrix, after: qualityAfter.snapshot.cameraWorldMatrix });
        check('quality-rebuild-disposes-previous-context', qualityAfter.lifecycle.filter(item => item.type === 'webglcontextlost').length >= 1, qualityAfter.lifecycle);
        await stopAndAssert(page, 'desktop-quality-stopped');
        policy = { mode: 'slow', scenario: 'desktop-cancel-both' };
        await page.locator('#enable-3d').click(); await waitDownloadingBoth(page);
        const cancelRows = modelRows('desktop-cancel-both'); check('cancel-has-two-active-downloads', cancelRows.length === 2 && cancelRows.every(row => !row.closed), cancelRows);
        await stopAndAssert(page, 'desktop-cancelled-both', cancelRows);
        policy = { mode: 'fast', scenario: 'desktop-retry-both' };
        await page.locator('#enable-3d').click(); await interactive(page); const retry = await stage(page, 'desktop-retry-ready');
        check('unified-cancel-retry-loads-complete-scene', retry.snapshot.sceneAssetsReady && modelRows('desktop-retry-both').length === 2);
        await stopAndAssert(page, 'desktop-before-navigation-stop');
        policy = { mode: 'slow', scenario: 'desktop-leave-loading' };
        await page.locator('#enable-3d').click(); await waitDownloadingBoth(page); const leaving = modelRows('desktop-leave-loading');
        await captureTelemetry(page, 'desktop-before-navigation');
        await page.locator('#read-articles').click(); await page.waitForURL(base + '/blog/'); await until(() => leaving.every(row => row.closed));
        check('article-navigation-aborts-both-model-requests', leaving.length === 2 && leaving.every(row => !row.completed && row.bytesSent < row.fileBytes), leaving);
        const article = page.locator('a[href*="/blog/posts/"]').first(); await article.click(); await page.waitForURL(/\/blog\/posts\//);
        const articleText = await page.locator('main').innerText();
        check('article-readable-after-loading-navigation', articleText.trim().length > 100 && await page.locator('h1').first().isVisible(), { url: page.url(), text: articleText.slice(0, 400) });
        await stage(page, 'desktop-article-readable');
      } finally { await captureTelemetry(page, 'desktop-final-document'); await context.close(); }
    });
    await runCase('http', async () => {
      policy = { mode: 'archive-error', scenario: 'archive-503' }; const { context, page } = await fresh('http');
      try {
        await page.locator('#enable-3d').click(); await page.locator('#disable-3d').focus();
        await page.waitForFunction(() => document.body.dataset.ready === 'fallback');
        await until(() => modelRows('archive-503').length === 2 && modelRows('archive-503').every(row => row.closed)); await delay(200);
        const failed = await stage(page, 'archive-503-whole-scene-fallback');
        const rows = modelRows('archive-503'), exterior = rows.find(row => row.scope === 'exterior');
        check('archive-failure-aborts-exterior', rows.find(row => row.scope === 'archive')?.status === 503 && exterior && !exterior.completed && exterior.bytesSent < exterior.fileBytes, rows);
        check('one-asset-failure-is-whole-scene-fallback', failed.ready === 'fallback' && failed.canvas === 0 && failed.posterVisible && failed.enableVisible && failed.snapshot.failureCode === 'LOAD_FAILED' && /重试|Retry/.test(failed.enableText) && failed.activeElement === 'enable-3d', failed);
        check('archive-http-503-observed-by-browser', report.responses.some(row => row.case === 'http' && row.status === 503 && new URL(row.url).pathname === assetPaths.archive));
        await until(() => page.workers().length === 0);
        policy = { mode: 'fast', scenario: 'archive-503-retry' }; await page.locator('#enable-3d').click(); await interactive(page);
        const recovered = await stage(page, 'archive-503-retry-complete');
        check('failed-unified-scene-retry-recovers-both-assets', recovered.snapshot.sceneAssetsReady && recovered.snapshot.interiorLoaded && !recovered.snapshot.failureCode && modelRows('archive-503-retry').length === 2);
        await stopAndAssert(page, 'http-recovered-stopped');
      } finally { await captureTelemetry(page, 'http'); await context.close(); }
    });
    await runCase('decoder', async () => {
      if (Object.values(assetInspection).every(asset => asset.dracoPrimitiveCount === 0)) {
        return { result: 'NOT_APPLICABLE_CURRENT_ASSETS', reason: 'The pinned production GLBs contain no KHR_draco_mesh_compression primitives. They never request Draco decoder files, so this real-browser decoder initialization race cannot be exercised with these assets.', assetInspection };
      }
      policy = { mode: 'decoder-delay', scenario: 'decoder-initialization-cancel' };
      const { context, page } = await fresh('decoder');
      try {
        await page.locator('#enable-3d').click();
        await until(() => modelRows('decoder-initialization-cancel').length === 2 && modelRows('decoder-initialization-cancel').every(row => row.completed), 45000);
        await until(() => report.serverRequests.filter(row => row.scenario === 'decoder-initialization-cancel' && row.decoderAsset && !row.closed).length === 2, 45000);
        const pending = await stage(page, 'decoder-initialization-pending');
        const decoderRows = report.serverRequests.filter(row => row.scenario === 'decoder-initialization-cancel' && row.decoderAsset);
        check('decoder-cancel-occurs-after-both-model-transfers', pending.ready === 'loading' && pending.visibleCanvas === 0 && pending.snapshot.loadProgress.loaded === totalBytes && decoderRows.length === 2 && decoderRows.every(row => !row.closed && row.bytesSent === 0), { progress: pending.snapshot.loadProgress, decoderRows });
        const cancelledAt = Date.now();
        await stopAndAssert(page, 'decoder-initialization-cancelled');
        await until(() => decoderRows.every(row => row.closed), 15000); await delay(1800);
        const settled = await stage(page, 'decoder-late-responses-settled');
        const lateWorkers = report.workers.filter(row => row.case === 'decoder');
        check('decoder-cancel-does-not-retain-late-workers', page.workers().length === 0 && lateWorkers.every(row => row.closed), { cancelledAt, workers: lateWorkers, decoderRows });
        check('decoder-cancel-cannot-restore-stale-viewer', settled.ready === 'static' && settled.canvas === 0 && settled.posterVisible && !settled.snapshot.failureCode && settled.activeElement === 'enable-3d', settled);
        policy = { mode: 'fast', scenario: 'decoder-cancel-retry' };
        await page.locator('#enable-3d').click(); await interactive(page);
        const retried = await stage(page, 'decoder-cancel-retry-ready');
        check('decoder-init-cancel-allows-clean-retry', retried.snapshot.sceneAssetsReady && retried.snapshot.interiorLoaded && modelRows('decoder-cancel-retry').length === 2);
        await stopAndAssert(page, 'decoder-retry-released');
      } finally { await captureTelemetry(page, 'decoder'); await context.close(); }
    });
    await runCase('mobile', async () => {
      policy = { mode: 'slow', scenario: 'mobile-cancel-both' };
      const { context, page } = await fresh('mobile', { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 1 });
      try {
        const initial = await stage(page, 'mobile-static');
        check('mobile-touch-context-no-auto-download', initial.coarsePointer && !report.requests.some(row => row.case === 'mobile' && /\.glb(?:\?|$)/.test(row.url)), { coarsePointer: initial.coarsePointer, maxTouchPoints: initial.maxTouchPoints });
        await page.locator('#enable-3d').tap(); await waitDownloadingBoth(page); const progress = await stage(page, 'mobile-total-progress');
        check('mobile-touch-activates-one-total-progress', progress.snapshot.loadProgress.scope === 'scene' && progress.snapshot.loadProgress.total === totalBytes && progress.pointerEvents.some(event => event.target === 'enable-3d' && event.pointerType === 'touch' && event.isTrusted), progress.pointerEvents);
        const rows = modelRows('mobile-cancel-both'); await stopAndAssert(page, 'mobile-both-cancelled', rows, true);
        policy = { mode: 'fast', scenario: 'mobile-retry-both' }; await page.locator('#enable-3d').tap(); await interactive(page);
        const ready = await stage(page, 'mobile-unified-ready');
        check('mobile-default-light-both-resident', ready.snapshot.quality === 'light' && ready.snapshot.sceneAssetsReady && ready.snapshot.interiorLoaded && ready.canvas === 1 && !ready.posterVisible);
        const count = modelCount();
        for (let cycle = 0; cycle < 2; cycle++) {
          await enter(page, true); const archive = await stage(page, `mobile-archive-${cycle}`, cycle === 0);
          check(`mobile-archive-${cycle}-no-load`, archive.snapshot.state.mode === 'archive' && !archive.snapshot.loadProgress && archive.snapshot.interiorLoaded);
          await page.locator('#back').tap(); await delay(200);
        }
        check('mobile-switches-make-no-glb-requests', modelCount() === count, { before: count, after: modelCount() });
        const stopped = await stopAndAssert(page, 'mobile-scene-released', [], true);
        check('mobile-controls-trusted-touch-events', ['enable-3d', 'disable-3d', 'enter', 'back'].every(id => stopped.pointerEvents.some(event => event.target === id && event.pointerType === 'touch' && event.isTrusted)), stopped.pointerEvents);
      } finally { await captureTelemetry(page, 'mobile'); await context.close(); }
    });
    check('no-uncaught-browser-errors', report.pageErrors.length === 0, report.pageErrors);
  } catch (error) { report.runError = String(error.stack || error); process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    if (server) { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); }
    report.finished = new Date().toISOString();
    const passedApplicable = !report.runError && selectedCases.every(name => report.cases.some(row => row.name === name && ['PASS', 'NOT_APPLICABLE_CURRENT_ASSETS'].includes(row.result))) && report.assertions.every(row => row.pass);
    report.result = passedApplicable ? report.cases.some(row => row.result === 'NOT_APPLICABLE_CURRENT_ASSETS') ? 'PASS_WITH_NOT_APPLICABLE' : 'PASS' : 'FAIL';
    if (!passedApplicable) process.exitCode = 1;
    checkpoint(); console.log(JSON.stringify({ result: report.result, output, cases: report.cases, assertions: report.assertions.length, runError: report.runError }));
  }
})();
