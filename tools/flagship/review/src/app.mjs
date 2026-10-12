import catalog from 'virtual:review-catalog';
import { GestureTracker, initialState, reduce, cutawayOpen } from './interaction.mjs';
import './app.css';

const $ = (id) => document.getElementById(id);
const viewport = $('viewport');
const hotspot = $('hotspot');
viewport.append(hotspot);
const touch = matchMedia('(pointer: coarse)').matches;
let language = new URL(location.href).searchParams.get('lang') === 'en' ? 'en' : 'zh_CN';
let state = initialState();
let viewer = null;
let generation = 0;
let statusKey = '';
let staticMode = false;
let disposed = false;
let pendingViewer = null;
const gestures = new GestureTracker();
const abort = new AbortController();
const on = (element, name, fn, options = {}) => element.addEventListener(name, fn, { ...options, signal: abort.signal });
const t = (key) => catalog[language]['flagshipReview' + key];
const selectedQuality = () => $('quality').value;
function effectiveQuality() {
  const choice = selectedQuality();
  return choice === 'auto' ? ((touch || navigator.connection?.saveData || navigator.deviceMemory < 4) ? 'light' : 'standard') : choice;
}
function status(key = '') { statusKey = key; $('status').textContent = key ? t(key) : ''; }

function updateCopy() {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
  document.title = `kuhai · ${t(state.mode === 'archive' ? 'Archive' : 'Title')}`;
  document.querySelectorAll('[data-copy]').forEach((el) => { el.textContent = t(el.dataset.copy); });
  $('language').textContent = language === 'en' ? '中文' : 'EN';
  for (const [id, key] of [['language', 'Language'], ['settings-toggle', 'Settings'], ['settings', 'Settings'], ['hotspot', 'Select'], ['viewport', 'Title']]) $(id).setAttribute('aria-label', t(key));
  $('home').setAttribute('aria-label', `kuhai · ${t('Title')}`);
  updateUI();
  status(statusKey);
}
function updateUI() {
  const room = state.mode === 'archive';
  document.body.dataset.room = state.mode;
  $('room-title').textContent = t(room ? 'Archive' : 'Title');
  $('description').textContent = t(room ? 'ArchiveDesc' : 'Subtitle');
  $('eyebrow').textContent = room ? t('RoomStudy') : 'KUHAI / 02';
  $('back').hidden = !room;
  $('enter').hidden = room;
  $('enter').firstElementChild.textContent = t(state.selected ? 'Enter' : 'Archive');
  $('hint').textContent = room ? t('RoomStudy') : staticMode ? t('Static') : t(touch ? 'TouchHint' : 'DesktopHint');
  $('poster').alt = t(room ? 'RoomAlt' : 'PosterAlt');
  $('poster').src = room ? './assets/archive.webp?v=review-study-02' : './assets/overview.webp?v=review-study-02';
  hotspot.setAttribute('aria-expanded', String(cutawayOpen(state)));
  if (room || staticMode) hotspot.hidden = true;
  document.title = `kuhai · ${t(room ? 'Archive' : 'Title')}`;
}
function dispatch(event, historyMode = 'push') {
  const before = state;
  state = reduce(state, event);
  if (before.mode !== state.mode) {
    if (historyMode === 'push') history.pushState({ reviewRoom: state.mode }, '', state.mode === 'archive' ? '#archive' : location.pathname + location.search);
    if (state.mode === 'archive') $('room-title').focus({ preventScroll: true });
    else $('enter').focus({ preventScroll: true });
  }
  viewer?.update(state);
  updateUI();
}
function isHit(event) {
  return state.mode === 'ship' && (event.target.closest?.('#hotspot') || viewer?.hit(event.clientX, event.clientY));
}
on(viewport, 'pointerdown', (event) => {
  if (event.button !== 0) return;
  gestures.down(event.pointerId, event.clientX, event.clientY, !!isHit(event), event.pointerType);
});
on(viewport, 'pointermove', (event) => {
  gestures.move(event.pointerId, event.clientX, event.clientY);
  if (!gestures.active && event.pointerType === 'mouse') dispatch({ type: 'hover', value: !!isHit(event) });
});
on(viewport, 'pointerup', (event) => {
  const kind = gestures.up(event.pointerId, event.clientX, event.clientY, !!isHit(event));
  if (kind) dispatch({ type: 'activate', pointer: kind });
});
on(viewport, 'pointercancel', () => gestures.cancel());
on(viewport, 'lostpointercapture', () => gestures.cancel());
on(viewport, 'pointerleave', () => { if (!gestures.active) dispatch({ type: 'hover', value: false }); });
on(window, 'blur', () => { gestures.cancel(); dispatch({ type: 'hover', value: false }); });
on(hotspot, 'click', (event) => {
  if (event.detail === 0) dispatch({ type: 'activate', pointer: 'keyboard' });
});
on(hotspot, 'focus', () => dispatch({ type: 'focus', value: true }));
on(hotspot, 'blur', () => dispatch({ type: 'focus', value: false }));
on($('enter'), 'click', () => {
  if (staticMode || state.selected) dispatch({ type: 'enter' });
  else { dispatch({ type: 'select' }); viewer?.locate(); }
});
on($('back'), 'click', () => dispatch({ type: 'back' }));
on($('home'), 'click', (event) => { event.preventDefault(); dispatch({ type: 'back' }); });
on(window, 'popstate', () => dispatch({ type: location.hash === '#archive' ? 'enter' : 'back' }, 'none'));
on(window, 'hashchange', () => {
  const next = location.hash === '#archive' ? 'archive' : 'ship';
  if (next !== state.mode) dispatch({ type: next === 'archive' ? 'enter' : 'back' }, 'none');
});
on(window, 'keydown', (event) => {
  if (event.key === 'Escape') {
    if (!$('settings').hidden) toggleSettings(false);
    else dispatch({ type: 'escape' });
  }
});
on(viewport, 'keydown', (event) => {
  if (event.target !== viewport) return;
  if (viewer?.key(event.key)) event.preventDefault();
});
function toggleSettings(open) {
  $('settings').hidden = !open;
  $('settings-toggle').setAttribute('aria-expanded', String(open));
  if (open) $('quality').focus(); else $('settings-toggle').focus();
}
on($('settings-toggle'), 'click', () => toggleSettings($('settings').hidden));
on($('reset'), 'click', () => viewer?.reset());
on($('language'), 'click', () => {
  language = language === 'en' ? 'zh_CN' : 'en';
  const url = new URL(location.href);
  url.searchParams.set('lang', language === 'en' ? 'en' : 'zh');
  history.replaceState(history.state, '', url);
  updateCopy();
});
function fallback(failed = false) {
  staticMode = true;
  viewer?.dispose(); viewer = null;
  viewport.querySelector('canvas')?.remove();
  hotspot.hidden = true;
  $('poster').hidden = false;
  status(failed ? 'Failed' : '');
  updateUI();
}
async function mount() {
  const token = ++generation;
  pendingViewer?.abort(); pendingViewer = new AbortController();
  viewer?.dispose(); viewer = null;
  viewport.querySelector('canvas')?.remove();
  $('poster').hidden = false;
  if (effectiveQuality() === 'static') { fallback(); return; }
  staticMode = false;
  status('Loading');
  let instance;
  try {
    const { createViewer } = await import('./viewer.mjs');
    if (token !== generation || disposed) return;
    instance = await createViewer({ viewport, hotspot, quality: effectiveQuality(),
      signal: pendingViewer.signal,
      state: () => state,
      onLoading: (loading) => { if (token === generation && !disposed) status(loading ? 'Loading' : ''); },
      onError: () => { if (token === generation && !disposed) { ++generation; fallback(true); } }
    });
    if (token !== generation || disposed) { instance.dispose(); return; }
    viewer = instance;
    viewer.update(state);
    $('poster').hidden = true;
    status(); updateUI();
  } catch (error) {
    instance?.dispose();
    if (token === generation && !disposed) { console.warn('Flagship viewer unavailable:', error); fallback(true); }
  }
}
on($('quality'), 'change', mount);
on(document, 'visibilitychange', () => { if (document.hidden) gestures.cancel(); });
on(window, 'pagehide', (event) => {
  if (!event.persisted) { disposed = true; generation++; abort.abort(); pendingViewer?.abort(); viewer?.dispose(); }
});
updateCopy();
if (location.hash === '#archive') dispatch({ type: 'enter' }, 'none');
// Save-data is a user preference; don't start the expensive path without opting in.
if (navigator.connection?.saveData) $('quality').value = 'static';
mount();
