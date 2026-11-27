// Controlled local-network regression checks. This does not certify the live site
// or change the source model's browserAcceptance / lightingCalibrated flags.
// node accept-3d-loading.cjs --dist=... --output=... --firefox=... --playwright=... [--case=mobile]
'use strict';
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const assert = require('node:assert/strict');
const { setTimeout: delay } = require('node:timers/promises');

const args = {};
for (const argument of process.argv.slice(2)) {
  const match = /^--(dist|output|firefox|playwright|rate|case)=(.+)$/.exec(argument);
  if (!match || args[match[1]]) throw Error('Expected unique --dist, --output, --firefox, --playwright and optional --rate / --case arguments');
  args[match[1]] = match[2];
}
for (const key of ['dist', 'output', 'firefox', 'playwright']) if (!args[key]) throw Error(`Missing --${key}`);
const caseNames = { desktop: 'desktop-streaming-cancel-retry-navigation', http: 'controlled-http-error-recovery', mobile: 'mobile-touch-cancel-retry' };
const requestedCase = args.case || 'all';
if (requestedCase !== 'all' && !Object.hasOwn(caseNames, requestedCase)) throw Error('--case must be all, desktop, http, or mobile');
const selectedCases = requestedCase === 'all' ? Object.values(caseNames) : [caseNames[requestedCase]];
const dist = fs.realpathSync(args.dist), output = path.resolve(args.output), rate = Number(args.rate || 360000);
if (!Number.isFinite(rate) || rate < 100000 || rate > 360000) throw Error('--rate must be 100000..360000 bytes/second');
for (const file of ['index.html', 'blog/index.html', 'assets/p23-asset-contract.json'])
  if (!fs.statSync(path.join(dist, file)).isFile()) throw Error(`Missing assembled distribution file: ${file}`);
const relativeOutput = path.relative(dist, output);
if (!relativeOutput.startsWith('..' + path.sep) && relativeOutput !== '..' && !path.isAbsolute(relativeOutput))
  throw Error('Evidence output must be outside the distribution');
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.mkdirSync(output); // Never overwrite previous evidence.
const { firefox } = require(path.resolve(args.playwright));
const contract = JSON.parse(fs.readFileSync(path.join(dist, 'assets/p23-asset-contract.json'), 'utf8'));
const assetPaths = Object.fromEntries(Object.entries(contract.assets).map(([scope, asset]) => [scope, new URL(asset.uri, 'http://localhost/').pathname]));
const report = {
  schema: 'controlled-network-3d-loading-v1', started: new Date().toISOString(),
  scope: 'Local assembled distribution; controlled streaming / cancellation / HTTP 503. Not live-site acceptance.',
  dist, firefox: path.resolve(args.firefox), playwright: path.resolve(args.playwright), rateBytesPerSecond: rate,
  engine: 'Existing Firefox headless; fresh isolated contexts; default WebGL settings',
  mobile: '390x844 viewport with hasTouch; Firefox touch emulation, not a physical mobile device',
  requestedCase, selectedCases, expectedCaseCount: selectedCases.length,
  source: contract.source_scene, modelPins: contract.assets,
  requests: [], requestFailures: [], responses: [], console: [], pageErrors: [], serverRequests: [], stages: [], assertions: [], cases: [],
};
let policy = { mode: 'fast', scenario: 'startup' }, browser, base, server;
const consoleJobs = [], sockets = new Set();
const checkpoint = () => fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2) + '\n');
function check(name, condition, detail) {
  report.assertions.push({ name, pass: !!condition, detail }); checkpoint();
  assert.ok(condition, `${name}${detail ? ': ' + JSON.stringify(detail) : ''}`);
}
async function until(predicate, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { const value = predicate(); if (value) return value; await delay(50); }
  throw Error('Timed out waiting for server evidence');
}
function contentType(file) {
  return ({ '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript',
    '.json': 'application/json', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.svg': 'image/svg+xml',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2' })[path.extname(file)] || 'application/octet-stream';
}
async function serve(req, res) {
  const started = Date.now(), selectedPolicy = { ...policy };
  const row = { id: report.serverRequests.length + 1, method: req.method, url: req.url, started: new Date(started).toISOString(),
    scenario: selectedPolicy.scenario, mode: selectedPolicy.mode, bytesSent: 0 };
  report.serverRequests.push(row);
  let stream;
  res.on('close', () => {
    row.closed = true; row.completed = res.writableFinished; row.durationMs = Date.now() - started;
    row.endReason = res.writableFinished ? 'complete' : 'client-aborted'; stream?.destroy();
  });
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1/').pathname);
    let file = path.resolve(dist, '.' + pathname), relative = path.relative(dist, file);
    if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('outside distribution');
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    file = fs.realpathSync(file); relative = path.relative(dist, file);
    if (relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('outside distribution');
    const stat = fs.statSync(file), isModel = path.extname(file) === '.glb';
    row.path = pathname; row.fileBytes = stat.size;
    row.scope = Object.keys(assetPaths).find(scope => assetPaths[scope] === pathname) || null;
    if (isModel && selectedPolicy.mode === 'http-error') {
      // Keep the real request pending long enough to focus its cancel control.
      await delay(1500);
      if (res.destroyed) return;
      row.status = 503; res.writeHead(503, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' });
      res.end('Controlled acceptance-test HTTP 503'); return;
    }
    row.status = 200;
    res.writeHead(200, { 'Content-Type': contentType(file), 'Content-Length': stat.size, 'Cache-Control': 'no-store' });
    if (req.method === 'HEAD') { res.end(); return; }
    const slow = isModel && selectedPolicy.mode === 'slow';
    // Real chunked delivery over the socket, with a delay before each 100ms slice.
    // No Playwright response fulfillment, synthetic progress, or browser timers.
    stream = fs.createReadStream(file, { highWaterMark: slow ? Math.floor(rate / 10) : 256 * 1024 });
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
    if (res.destroyed) return;
    row.error = String(error);
    if (!res.headersSent) { row.status = 404; res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('Not found'); }
    else res.destroy(error);
  }
}
function instrument(page, name) {
  page.on('request', request => report.requests.push({ case: name, at: Date.now(), url: request.url(), method: request.method(), type: request.resourceType() }));
  page.on('response', response => report.responses.push({ case: name, url: response.url(), status: response.status(), contentLength: response.headers()['content-length'] }));
  page.on('requestfailed', request => report.requestFailures.push({ case: name, url: request.url(), failure: request.failure(), timing: request.timing() }));
  page.on('pageerror', error => report.pageErrors.push({ case: name, error: String(error.stack || error) }));
  page.on('console', message => {
    const row = { case: name, type: message.type(), text: message.text(), location: message.location() }; report.console.push(row);
    consoleJobs.push(Promise.all(message.args().map(argument => argument.evaluate(value => value instanceof Error
      ? { name: value.name, message: value.message, stack: value.stack, code: value.code } : String(value)).catch(String))).then(values => { row.arguments = values; }));
  });
}
async function state(page) {
  return page.evaluate(() => ({ url: location.href, secure: isSecureContext, language: document.documentElement.lang,
    ready: document.body.dataset.ready, status: document.getElementById('status')?.textContent, activeElement: document.activeElement?.id,
    posterVisible: !!document.getElementById('poster') && !document.getElementById('poster').hidden,
    canvas: document.querySelectorAll('#viewport canvas').length, busy: document.getElementById('viewport')?.getAttribute('aria-busy'),
    enableVisible: !!document.getElementById('enable-3d') && !document.getElementById('enable-3d').hidden,
    disableVisible: !!document.getElementById('disable-3d') && !document.getElementById('disable-3d').hidden,
    enableText: document.getElementById('enable-3d')?.textContent, maxTouchPoints: navigator.maxTouchPoints,
    coarsePointer: matchMedia('(pointer: coarse)').matches, pointerEvents: window.__loadingAcceptancePointerEvents || [],
    snapshot: window.__flagshipReview?.snapshot(),
  }));
}
async function stage(page, name, screenshot = true) {
  const value = await state(page);
  report.stages.push({ stage: name, at: new Date().toISOString(), state: value });
  if (screenshot) await page.screenshot({ path: path.join(output, name + '.png'), fullPage: false });
  checkpoint(); console.log(JSON.stringify({ stage: name, ready: value.ready, status: value.status, progress: value.snapshot?.loadProgress }));
  return value;
}
async function waitDownload(page, scope = 'exterior') {
  await page.waitForFunction(scope => {
    const progress = window.__flagshipReview?.snapshot().loadProgress;
    return progress?.scope === scope && progress.phase === 'downloading' && progress.loaded > 0 && progress.loaded < progress.total;
  }, scope, { timeout: 45000 });
}
async function interactive(page, archive = false) {
  await page.waitForFunction(archive => {
    const snapshot = window.__flagshipReview?.snapshot();
    return document.body.dataset.ready === 'fallback' || (document.body.dataset.ready === 'interactive' && (!archive || (snapshot?.interiorLoaded && !snapshot.interiorLoading)));
  }, archive, { timeout: 180000 });
  assert.equal((await state(page)).ready, 'interactive', 'Load reached failure fallback before becoming interactive');
}
async function enterArchive(page, touch = false) {
  for (let attempt = 0; attempt < 2; attempt++) {
    if ((await state(page)).snapshot?.state.mode === 'archive') break;
    await page.locator('#enter')[touch ? 'tap' : 'click']();
  }
}
async function cancelled(page, label, serverRow, touch = false) {
  await page.locator('#disable-3d')[touch ? 'tap' : 'click']();
  await page.waitForFunction(() => document.body.dataset.ready === 'static' && document.querySelectorAll('#viewport canvas').length === 0);
  await until(() => serverRow.closed);
  const value = await stage(page, label);
  check(label + '-request-aborted', !serverRow.completed && serverRow.bytesSent < serverRow.fileBytes, serverRow);
  check(label + '-clean-static', value.canvas === 0 && value.posterVisible && value.enableVisible && !value.disableVisible && !value.snapshot.loadProgress && !value.snapshot.failureCode, value);
}
const latestModel = scope => report.serverRequests.findLast(row => row.scope === scope && !row.closed);
async function freshPage(name, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', ...options });
  const page = await context.newPage(); page.setDefaultTimeout(20000); instrument(page, name);
  await page.goto(base + '/?qa=1', { waitUntil: 'networkidle' });
  return { context, page };
}
async function runCase(name, body) {
  if (!selectedCases.includes(name)) return;
  const row = { name, started: new Date().toISOString() }; report.cases.push(row);
  try { await body(); row.result = 'PASS'; }
  catch (error) { row.result = 'FAIL'; row.error = String(error.stack || error); process.exitCode = 1; }
  finally { row.finished = new Date().toISOString(); checkpoint(); console.log(JSON.stringify(row)); }
}

(async () => {
  try {
    server = http.createServer((req, res) => { void serve(req, res); });
    server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    base = 'http://127.0.0.1:' + server.address().port; report.base = base;
    browser = await firefox.launch({ headless: true, executablePath: path.resolve(args.firefox) });
    report.browserVersion = browser.version();

    await runCase('desktop-streaming-cancel-retry-navigation', async () => {
      policy = { mode: 'slow', scenario: 'desktop-slow-success' };
      const { context, page } = await freshPage('desktop');
      try {
        const initial = await stage(page, 'desktop-default-static');
        check('default-is-static-without-model-download', initial.ready === 'static' && initial.canvas === 0 && !report.requests.some(row => /\.glb(?:\?|$)/.test(row.url)));
        const clicked = Date.now(); await page.locator('#enable-3d').click(); await waitDownload(page);
        await delay(Math.max(0, 32000 - (Date.now() - clicked)));
        const slow = await stage(page, 'desktop-progress-after-32s');
        check('download-remains-active-beyond-30s', Date.now() - clicked >= 32000 && slow.ready === 'loading' && slow.snapshot.loadProgress?.scope === 'exterior' && slow.snapshot.loadProgress.loaded > 0 && slow.snapshot.loadProgress.loaded < slow.snapshot.loadProgress.total && slow.disableVisible, slow);
        await page.locator('#language').click();
        const english = await stage(page, 'desktop-progress-english');
        check('loading-status-switches-to-english', english.language === 'en' && /Downloading/.test(english.status) && /%/.test(english.status), english.status);
        await page.locator('#language').click();
        const chinese = await stage(page, 'desktop-progress-chinese');
        check('loading-status-switches-back-to-chinese', chinese.language === 'zh-CN' && /[\u3400-\u9fff]/.test(chinese.status) && /%/.test(chinese.status), chinese.status);
        await interactive(page);
        const ship = await stage(page, 'desktop-complete-exterior');
        const delivered = report.serverRequests.find(row => row.scope === 'exterior' && row.scenario === 'desktop-slow-success');
        check('real-slow-stream-delivered-complete-model', delivered.completed && delivered.bytesSent === contract.assets.exterior.bytes && delivered.durationMs > 60000, delivered);
        check('exterior-ready-clears-progress-and-keeps-provenance', ship.canvas === 1 && !ship.posterVisible && !ship.snapshot.loadProgress && ship.snapshot.browserAcceptance === false && ship.snapshot.modelSha256 === contract.assets.exterior.sha256, ship);
        await enterArchive(page); await waitDownload(page, 'archive'); await stage(page, 'desktop-interior-progress'); await interactive(page, true);
        const archive = await stage(page, 'desktop-complete-interior');
        check('interior-ready-clears-progress', archive.snapshot.state.mode === 'archive' && archive.snapshot.interiorLoaded && !archive.snapshot.loadProgress && archive.status === '', archive);

        await page.locator('#back').click(); await page.locator('#disable-3d').click();
        policy = { mode: 'slow', scenario: 'desktop-cancel-exterior' };
        await page.locator('#enable-3d').click(); await waitDownload(page);
        const pendingExterior = latestModel('exterior'); check('desktop-cancel-has-live-request', !!pendingExterior);
        await cancelled(page, 'desktop-cancelled-exterior', pendingExterior);
        policy = { mode: 'fast', scenario: 'desktop-retry-exterior' };
        await page.locator('#enable-3d').click(); await interactive(page); await stage(page, 'desktop-retried-exterior');
        check('desktop-retry-completes', (await state(page)).ready === 'interactive');

        policy = { mode: 'slow', scenario: 'desktop-cancel-interior' };
        await enterArchive(page); await waitDownload(page, 'archive'); const pendingInterior = latestModel('archive');
        await page.locator('#back').click(); await until(() => pendingInterior.closed);
        const backed = await stage(page, 'desktop-cancelled-interior');
        check('back-cancels-interior-without-destroying-exterior', !pendingInterior.completed && backed.canvas === 1 && backed.ready === 'interactive' && !backed.snapshot.interiorLoading && !backed.snapshot.interiorLoaded && !backed.snapshot.loadProgress, backed);
        policy = { mode: 'fast', scenario: 'desktop-retry-interior' };
        await enterArchive(page); await interactive(page, true); await stage(page, 'desktop-retried-interior');
        check('interior-retry-completes', (await state(page)).snapshot.interiorLoaded);

        await page.locator('#back').click(); await page.locator('#disable-3d').click();
        policy = { mode: 'slow', scenario: 'desktop-leave-during-download' };
        await page.locator('#enable-3d').click(); await waitDownload(page); const leaving = latestModel('exterior');
        await page.locator('#read-articles').click(); await page.waitForURL(base + '/blog/'); await until(() => leaving.closed);
        check('navigation-aborts-inflight-model', !leaving.completed && leaving.bytesSent < leaving.fileBytes, leaving);
        const article = page.locator('a[href*="/blog/posts/"]').first(); await article.waitFor({ state: 'visible' });
        await article.click(); await page.waitForURL(/\/blog\/posts\//);
        const text = await page.locator('main').innerText();
        check('article-remains-readable-after-leaving-loading', text.trim().length > 100 && await page.locator('h1').first().isVisible(), { url: page.url(), text: text.slice(0, 700) });
        await stage(page, 'desktop-readable-article');
      } finally { await context.close(); }
    });

    await runCase('controlled-http-error-recovery', async () => {
      policy = { mode: 'http-error', scenario: 'desktop-controlled-http-error' };
      const { context, page } = await freshPage('http-error');
      try {
        await page.locator('#enable-3d').click();
        await page.locator('#disable-3d').focus();
        check('cancel-control-focused-before-http-error', (await state(page)).activeElement === 'disable-3d');
        await page.waitForFunction(() => document.body.dataset.ready === 'fallback');
        const failed = await stage(page, 'desktop-http-error-fallback');
        check('http-failure-shows-retry-and-static-fallback', failed.canvas === 0 && failed.posterVisible && failed.enableVisible && failed.snapshot.failureCode === 'LOAD_FAILED' && !!failed.status && /重试|Retry/.test(failed.enableText), failed);
        check('failure-restores-focus-to-retry', failed.activeElement === 'enable-3d', failed.activeElement);
        check('controlled-http-503-observed', report.responses.some(row => row.case === 'http-error' && row.status === 503 && /\.glb(?:\?|$)/.test(row.url)));
        policy = { mode: 'fast', scenario: 'desktop-http-error-retry' };
        await page.locator('#enable-3d').click(); await interactive(page);
        const recovered = await stage(page, 'desktop-http-error-recovered');
        check('http-retry-restores-interactive-view', recovered.canvas === 1 && !recovered.snapshot.failureCode && !recovered.snapshot.loadProgress && recovered.status === '', recovered);
      } finally { await context.close(); }
    });

    await runCase('mobile-touch-cancel-retry', async () => {
      policy = { mode: 'slow', scenario: 'mobile-cancel-exterior' };
      const { context, page } = await freshPage('mobile', { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 1 });
      try {
        // Observe native events emitted by Playwright's .tap(), without altering
        // navigator. Firefox may expose maxTouchPoints=0 even with hasTouch=true.
        await page.evaluate(() => {
          window.__loadingAcceptancePointerEvents = [];
          document.addEventListener('pointerdown', event => window.__loadingAcceptancePointerEvents.push({
            pointerType: event.pointerType, isTrusted: event.isTrusted,
            target: event.target.closest?.('button')?.id || event.target.id, at: performance.now(),
          }), { capture: true });
        });
        const initial = await stage(page, 'mobile-default-static');
        check('mobile-coarse-pointer-context-active', initial.coarsePointer, { coarsePointer: initial.coarsePointer, maxTouchPoints: initial.maxTouchPoints });
        check('mobile-default-has-no-model-request', !report.requests.some(row => row.case === 'mobile' && /\.glb(?:\?|$)/.test(row.url)));
        await page.locator('#enable-3d').tap();
        const touchInput = (await state(page)).pointerEvents;
        check('mobile-tap-produces-trusted-touch-pointerdown', touchInput.some(event => event.target === 'enable-3d' && event.pointerType === 'touch' && event.isTrusted), touchInput);
        await waitDownload(page); await stage(page, 'mobile-progress');
        const active = latestModel('exterior'); await cancelled(page, 'mobile-cancelled', active, true);
        policy = { mode: 'fast', scenario: 'mobile-retry-exterior' };
        await page.locator('#enable-3d').tap(); await interactive(page);
        const finished = await stage(page, 'mobile-retried-complete');
        check('mobile-retry-completes-with-light-quality', finished.canvas === 1 && !finished.posterVisible && !finished.snapshot.loadProgress && finished.snapshot.quality === 'light', finished);
        await enterArchive(page, true); await interactive(page, true);
        const archive = await stage(page, 'mobile-interior-complete');
        check('mobile-interior-is-available', archive.snapshot.interiorLoaded && archive.snapshot.state.mode === 'archive' && !archive.snapshot.loadProgress, archive);
        await page.locator('#disable-3d').tap();
        const stopped = await stage(page, 'mobile-stopped-cleanly'); check('mobile-stop-removes-canvas', stopped.canvas === 0 && stopped.ready === 'static' && stopped.posterVisible, stopped);
        check('mobile-controls-received-real-touch-input', ['enable-3d', 'disable-3d', 'enter'].every(id => stopped.pointerEvents.some(event => event.target === id && event.pointerType === 'touch' && event.isTrusted)), stopped.pointerEvents);
      } finally { await context.close(); }
    });
    check('no-uncaught-browser-errors', report.pageErrors.length === 0, report.pageErrors);
  } catch (error) { report.runError = String(error.stack || error); process.exitCode = 1; }
  finally {
    await Promise.allSettled(consoleJobs);
    if (browser) await browser.close();
    if (server) { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); }
    report.finished = new Date().toISOString();
    report.result = !report.runError && report.cases.length === report.expectedCaseCount && selectedCases.every(name => report.cases.some(row => row.name === name && row.result === 'PASS')) && report.assertions.every(row => row.pass) ? 'PASS' : 'FAIL';
    if (report.result !== 'PASS') process.exitCode = 1;
    checkpoint(); console.log(JSON.stringify({ result: report.result, output, selectedCases, expectedCaseCount: report.expectedCaseCount, cases: report.cases, assertions: report.assertions.length, runError: report.runError }));
  }
})();
