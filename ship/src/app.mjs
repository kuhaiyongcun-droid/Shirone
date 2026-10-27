import catalog from 'virtual:review-catalog';
import site from 'virtual:ship-config';
import { GestureTracker, initialState, reduce, cutawayOpen } from './interaction.mjs';
import { loadContractBundle } from './asset-contract.mjs';
import { presentationInsets } from './presentation-layout.mjs';
import './app.css';

const $ = id => document.getElementById(id);
const viewport = $('viewport'), hotspot = $('hotspot');
viewport.append(hotspot);
const params = new URL(location.href).searchParams;
const touch = matchMedia('(pointer: coarse)').matches;
let language = params.get('lang') === 'en' ? 'en' : 'zh_CN';
let state = initialState(), viewer = null, runtime = null, generation = 0;
let disposed = false, loading = false, staticMode = true, statusKey = '';
let pendingViewer = null, shownScope = null, previousSnapshot = null;
let loadProgress = null, failureCode = '', progressPaintedAt = 0;
const viewByScope = {}, gestures = new GestureTracker(), events = new AbortController();
const on = (el, name, fn, options = {}) => el.addEventListener(name, fn, { ...options, signal: events.signal });
const t = key => catalog[language][key.startsWith('Ship') ? 'flagship' + key : 'flagshipReview' + key];
if (['neutral', 'space'].includes(params.get('light'))) $('review-light').value = params.get('light');
if (['auto', 'standard', 'light'].includes(params.get('quality'))) $('quality').value = params.get('quality');
$('matched-frame').checked = false;
if (params.get('qa') === '1') document.querySelectorAll('[data-qa]').forEach(el => el.hidden = false);
const reviewSettings = () => ({ view: $('review-view').value, lighting: $('review-light').value,
  group: $('service-group').value || 'all', matched: $('matched-frame').checked, gain: Number($('lamp-gain').value) });
function effectiveQuality() {
  const choice = $('quality').value;
  return choice === 'auto' ? (touch || navigator.connection?.saveData || navigator.deviceMemory < 4 ? 'light' : 'standard') : choice;
}
function renderStatus() {
  let text = statusKey ? t(statusKey) : '';
  if (statusKey === 'Failed') {
    if (failureCode === 'ASSET_IDLE_TIMEOUT') text = t('ShipLoadIdleTimeout');
    if (failureCode === 'ASSET_TOTAL_TIMEOUT') text = t('ShipLoadTotalTimeout');
  }
  if (loadProgress) {
    const { phase, loaded, total } = loadProgress;
    const key = phase === 'downloading' ? 'ShipDownloading' : phase === 'verifying' ? 'ShipVerifying' : 'ShipDecoding';
    const values = { percent: Math.min(100, Math.floor(loaded / total * 100)), loaded: (loaded / 1e6).toFixed(1), total: (total / 1e6).toFixed(1) };
    text = t(key).replace(/\{(percent|loaded|total)\}/g, (_, name) => values[name]);
  }
  if ($('status').textContent !== text) $('status').textContent = text;
}
function status(key = '') { statusKey = key; loadProgress = null; renderStatus(); }
function reportProgress(progress) {
  const phaseChanged = loadProgress?.phase !== progress.phase;
  loadProgress = progress;
  // Limit live-region announcements during streaming; always show stage changes.
  if (phaseChanged || performance.now() - progressPaintedAt >= 500 || progress.loaded === progress.total) {
    progressPaintedAt = performance.now(); renderStatus();
  }
}
function configureControls() {
  if (!runtime?.ready) return;
  const scope = state.mode === 'archive' ? 'archive' : 'exterior';
  const rows = runtime.cameras.views.filter(row => row.scope === scope);
  if (shownScope !== scope) {
    const requested = rows.some(row => row.id === params.get('view')) ? params.get('view') : null;
    $('review-view').replaceChildren(...rows.map(row => {
      const o = document.createElement('option'); o.value = row.id; o.textContent = row.label[language]; return o;
    }));
    $('review-view').value = viewByScope[scope] || requested || runtime.cameras.defaults[scope];
    shownScope = scope;
    viewer?.setReview(reviewSettings());
  } else for (const option of $('review-view').options) option.textContent = rows.find(row => row.id === option.value).label[language];
  const current = $('service-group').value || 'all';
  const groups = [...new Set(runtime.lighting.lights.map(row => row.group))].filter(g => !['key', 'fill'].includes(g));
  $('service-group').replaceChildren(...['all', ...groups, 'off'].map(group => {
    const o = document.createElement('option'); o.value = group;
    o.textContent = group === 'all' ? t('LightsAll') : group === 'off' ? t('LightsOff') : runtime.lighting.group_labels?.[group]?.[language] || group;
    return o;
  }));
  $('service-group').value = ['all', ...groups, 'off'].includes(current) ? current : 'all';
}
function updatePoster() {
  const room = state.mode === 'archive', settings = reviewSettings();
  const row = runtime?.references.frames.find(row => row.scope === (room ? 'archive' : 'exterior') && row.view_id === settings.view && row.light === settings.lighting);
  // Every URI below is bound to verified build inputs; no model is fetched for the poster.
  const uri = row?.asset.uri || site.posters[room ? 'archive' : 'ship'];
  if ($('poster').getAttribute('src') !== uri) $('poster').src = uri;
  $('poster').hidden = !!viewer && !staticMode;
  $('reference-note').hidden = $('poster').hidden;
}
let lastLayout='';
function updatePresentationLayout(){
  const matched=$('matched-frame').checked;
  document.body.dataset.framing=matched?'reference':'presentation';
  const insets=presentationInsets(viewport,matched),key=JSON.stringify([viewport.clientWidth,viewport.clientHeight,matched,insets]);
  if(key!==lastLayout){lastLayout=key;viewer?.resize();}
}
const layoutObserver=new ResizeObserver(updatePresentationLayout);
for(const element of [$('experience'),document.querySelector('.masthead'),document.querySelector('.footer')])layoutObserver.observe(element);
function updateUI() {
  configureControls();
  const room = state.mode === 'archive', interactive = !!viewer && !staticMode;
  document.body.dataset.room = state.mode;
  document.body.dataset.interactive = String(interactive);
  document.body.dataset.ready = loading ? 'loading' : interactive ? 'interactive' : statusKey === 'Failed' ? 'fallback' : 'static';
  viewport.tabIndex = interactive ? 0 : -1;
  $('room-title').textContent = t(room ? 'Archive' : 'Title');
  $('description').textContent = t(room ? 'ArchiveDesc' : 'Subtitle');
  $('eyebrow').textContent = room ? 'KUHAI · ARCHIVE' : 'KUHAI · LOGBOOK';
  $('back').hidden = !room;
  $('enter').hidden = room || !interactive;
  $('enter').firstElementChild.textContent = t(state.selected ? 'Enter' : 'Archive');
  $('enable-3d').hidden = interactive || loading;
  $('enable-3d').textContent = t(statusKey === 'Failed' ? 'ShipRetry3D' : 'ShipEnable3D');
  $('disable-3d').hidden = !interactive && !loading;
  $('disable-3d').textContent = t(loading || statusKey === 'Loading' ? 'ShipCancelLoading' : 'ShipDisable3D');
  viewport.setAttribute('aria-busy', String(loading || statusKey === 'Loading'));
  $('settings-toggle').hidden = !interactive;
  $('recommend-view').hidden = !interactive || !room || $('matched-frame').checked;
  $('recommend-view').textContent = language === 'en' ? 'Reset view' : '推荐视角';
  $('recommend-view').title = language === 'en' ? 'Restore the recommended view' : '恢复当前机位的推荐视角';
  $('recommend-view').setAttribute('aria-label', $('recommend-view').title);
  $('review-view').disabled = !interactive;
  $('quality').disabled = loading;
  $('lamp-gain').disabled = $('service-group').value === 'off';
  $('gain-value').value = reviewSettings().gain.toFixed(2);
  $('hint').textContent = t(interactive ? touch ? 'TouchHint' : 'DesktopHint' : 'ShipStaticHint');
  if(interactive && room) $('hint').textContent = $('matched-frame').checked
    ? (language === 'en' ? 'Reference view · Camera locked' : '参考视角 · 相机已固定')
    : (language === 'en' ? 'Small view adjustments · Reset view to return' : '可小幅调整视角 · 点击推荐视角恢复');
  $('poster').alt = t(room ? 'RoomAlt' : 'PosterAlt');
  hotspot.setAttribute('aria-expanded', String(cutawayOpen(state)));
  if (room || !interactive) hotspot.hidden = true;
  document.title = t(room ? 'Archive' : 'Title') + ' · ' + site.author;
  updatePoster();
  updatePresentationLayout();
}
function updateCopy() {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
  document.querySelectorAll('[data-copy]').forEach(el => el.textContent = t(el.dataset.copy));
  $('language').textContent = language === 'en' ? '中文' : 'EN';
  for (const [id, key] of [['language', 'Language'], ['settings-toggle', 'Settings'], ['settings', 'Settings'], ['hotspot', 'Select'], ['viewport', 'Title']]) $(id).setAttribute('aria-label', t(key));
  updateUI(); renderStatus();
}
function dispatch(event, historyMode = 'push') {
  if (event.type === 'hover' && state.hover === (state.mode === 'ship' && !!event.value)) return;
  const before = state; state = reduce(state, event);
  const changed = before.mode !== state.mode;
  if (changed && historyMode === 'push') history.pushState({ reviewRoom: state.mode }, '', state.mode === 'archive' ? '#archive' : location.pathname + location.search);
  viewer?.update(state);
  updateUI();
  // The destination button must be visible before requesting focus.
  if (changed) (state.mode === 'archive' ? $('room-title') : viewer ? $('enter') : $('enable-3d')).focus({ preventScroll: true });
}
function isHit(event) {
  const rect = hotspot.getBoundingClientRect();
  const buttonHit = !hotspot.hidden && event.target.closest?.('#hotspot') && event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
  return !!viewer && state.mode === 'ship' && (buttonHit || viewer.hit(event.clientX, event.clientY));
}
on(viewport, 'pointerdown', event => {
  if (!viewer || event.button !== 0) return;
  gestures.down(event.pointerId, event.clientX, event.clientY, !!isHit(event), event.pointerType);
  // The hotspot is a sibling of the canvas: retain its drag sequence without
  // extending OrbitControls' scroll-blocking surface beyond the actual canvas.
  if (event.target.closest?.('#hotspot')) hotspot.setPointerCapture(event.pointerId);
});
on(viewport, 'pointermove', event => {
  if (!viewer) return;
  gestures.move(event.pointerId, event.clientX, event.clientY);
  if (!gestures.active && event.pointerType === 'mouse') dispatch({ type: 'hover', value: !!isHit(event) });
});
on(viewport, 'pointerup', event => {
  const kind = gestures.up(event.pointerId, event.clientX, event.clientY, !!isHit(event));
  if (hotspot.hasPointerCapture(event.pointerId)) hotspot.releasePointerCapture(event.pointerId);
  if (kind) dispatch({ type: 'activate', pointer: kind });
});
on(viewport, 'pointercancel', () => gestures.cancel());
on(viewport, 'lostpointercapture', () => gestures.cancel());
on(viewport, 'pointerleave', () => { if (!gestures.active) dispatch({ type: 'hover', value: false }); });
on(window, 'blur', () => { gestures.cancel(); dispatch({ type: 'hover', value: false }); });
on(hotspot, 'click', event => { if (event.detail === 0) dispatch({ type: 'activate', pointer: 'keyboard' }); });
on(hotspot, 'focus', () => dispatch({ type: 'focus', value: true }));
on(hotspot, 'blur', () => dispatch({ type: 'focus', value: false }));
on($('enter'), 'click', () => {
  if (state.selected) dispatch({ type: 'enter' });
  else { dispatch({ type: 'select' }); const view = viewer?.locate(); if (view) { $('review-view').value = view; viewByScope.exterior = view; } updateUI(); }
});
on($('back'), 'click', () => dispatch({ type: 'back' }));
// The identity and article links are real, full-document navigations.
on(window, 'popstate', () => dispatch({ type: location.hash === '#archive' ? 'enter' : 'back' }, 'none'));
on(window, 'hashchange', () => {
  const next = location.hash === '#archive' ? 'archive' : 'ship';
  if (next !== state.mode) dispatch({ type: next === 'archive' ? 'enter' : 'back' }, 'none');
});
function toggleSettings(open, focus = true) {
  $('settings').hidden = !open; $('settings-toggle').setAttribute('aria-expanded', String(open));
  if (focus) (open ? $('quality') : $('settings-toggle')).focus({ preventScroll: true });
}
on(window, 'keydown', event => {
  if (event.key !== 'Escape') return;
  if (!$('settings').hidden) toggleSettings(false);
  else if (state.mode === 'archive') dispatch({ type: 'back' });
  else dispatch({ type: 'escape' });
});
on(viewport, 'keydown', event => { if (event.target === viewport && viewer?.key(event.key)) event.preventDefault(); });
on($('settings-toggle'), 'click', () => toggleSettings($('settings').hidden));
on($('settings-close'), 'click', () => toggleSettings(false));
function restoreRecommendedView(){
  gestures.cancel();viewer?.reset();toggleSettings(false,false);updateUI();
  if(viewer&&!staticMode)viewport.focus({preventScroll:true});
}
on($('reset'), 'click', restoreRecommendedView);
on($('recommend-view'), 'click', restoreRecommendedView);
for (const id of ['review-view', 'review-light', 'service-group', 'matched-frame', 'lamp-gain']) {
  on($(id), id === 'lamp-gain' ? 'input' : 'change', () => {
    if (id === 'review-view') viewByScope[state.mode === 'archive' ? 'archive' : 'exterior'] = $('review-view').value;
    viewer?.setReview(reviewSettings()); updateUI();
  });
}
on($('language'), 'click', () => {
  language = language === 'en' ? 'zh_CN' : 'en';
  const url = new URL(location.href); url.searchParams.set('lang', language === 'en' ? 'en' : 'zh');
  history.replaceState(history.state, '', url); updateCopy();
});
function stop({ failed = false, focus = false, error } = {}) {
  const focused = document.activeElement;
  const focusWillHide = viewport.contains(focused) || $('settings').contains(focused)
    || ['disable-3d', 'enter', 'settings-toggle', 'recommend-view'].some(id => $(id) === focused);
  ++generation; pendingViewer?.abort(); pendingViewer = null;
  if (viewer) previousSnapshot = viewer.snapshot();
  viewer?.dispose(); viewer = null; loading = false; staticMode = true;
  gestures.cancel(); state = { ...state, hover: false, selected: false, focus: false };
  viewport.querySelectorAll('canvas').forEach(canvas => canvas.remove());
  failureCode = failed ? error?.code || 'LOAD_FAILED' : '';
  toggleSettings(false, false); status(failed ? 'Failed' : ''); updateUI();
  if (focus || (failed && focusWillHide)) $('enable-3d').focus({ preventScroll: true });
}
async function mount() {
  if (disposed) return;
  const token = ++generation;
  pendingViewer?.abort(); pendingViewer = new AbortController();
  if (viewer) previousSnapshot = viewer.snapshot();
  viewer?.dispose(); viewer = null; loading = true; staticMode = true;
  if ($('quality').value === 'static') $('quality').value = 'auto';
  failureCode = ''; status('Loading'); updateUI();
  let instance;
  try {
    const bundle = runtime || await loadContractBundle(new URL(site.assetPin.contract.uri, document.baseURI), pendingViewer.signal, site.assetPin);
    if (token !== generation || disposed) return;
    runtime = bundle;
    if (!runtime.ready) throw Error('No accepted model assets');
    configureControls();
    const { createViewer } = await import('./contract-viewer.mjs');
    if (token !== generation || disposed) return;
    instance = await createViewer({ viewport, hotspot, quality: effectiveQuality(), review: reviewSettings(),
      initialSnapshot: previousSnapshot, signal: pendingViewer.signal, runtime, state: () => state,
      onLoading: value => { if (token === generation && !disposed) { status(value ? 'Loading' : ''); updateUI(); } },
      onProgress: progress => { if (token === generation && !disposed) reportProgress(progress); },
      onError: error => { if (token === generation && !disposed) stop({ failed: true, error, focus: document.activeElement === viewport }); }
    });
    if (token !== generation || disposed) { instance.dispose(); return; }
    viewer = instance; loading = false; staticMode = false;
    if (!viewer.snapshot().interiorLoading) status();
    viewer.update(state); viewer.setReview(reviewSettings()); updateUI();
    if (document.activeElement === $('enable-3d') || document.activeElement === document.body) viewport.focus({ preventScroll: true });
  } catch (error) {
    instance?.dispose();
    if (token === generation && !disposed) { console.warn('Flagship viewer unavailable:', error); stop({ failed: true, error, focus: document.activeElement === document.body }); }
  }
}
on($('enable-3d'), 'click', mount);
on($('disable-3d'), 'click', () => stop({ focus: true }));
on($('quality'), 'change', () => { if ($('quality').value === 'static') stop({ focus: true }); else mount(); });
on(document, 'visibilitychange', () => { if (document.hidden) gestures.cancel(); });
on(window, 'pagehide', event => {
  // BFCache also releases GPU resources; back navigation returns to the readable static page.
  stop();
  if (!event.persisted) { disposed = true; layoutObserver.disconnect(); events.abort(); }
});
on(window, 'pageshow', event => { if (event.persisted) { staticMode = true; loading = false; updateUI(); } });
$('language').hidden = false;
if (location.hash === '#archive') state = reduce(state, { type: 'enter' });
updateCopy();
// No mount here: the expensive path is only entered by an explicit button activation.
if (params.get('qa') === '1') window.__flagshipReview = Object.freeze({
  hitAtPoint: (x,y) => !!viewer?.hit(x,y),
  snapshot: () => ({ state: { ...state }, staticMode, loading, loadProgress: loadProgress ? { ...loadProgress } : null, failureCode, contractStatus: runtime?.contract.status || 'not-requested',
    sourceStage: site.sourceStage, browserAcceptance: false, lightingCalibrated: false, ...(viewer?.snapshot() || {}) })
});

