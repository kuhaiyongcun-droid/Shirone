// DOM/renderer independent: gestures never own camera or ship transforms.
export class GestureTracker {
  constructor(threshold = 7) { this.threshold = threshold; this.pointers = new Map(); }
  down(id, x, y, hit, type = 'mouse') {
    const multi = this.pointers.size > 0;
    if (multi) for (const p of this.pointers.values()) p.dragged = true;
    this.pointers.set(id, { x, y, hit, type, dragged: multi });
  }
  move(id, x, y) {
    const p = this.pointers.get(id);
    if (p && Math.hypot(x - p.x, y - p.y) > this.threshold) p.dragged = true;
  }
  up(id, x, y, hit) {
    this.move(id, x, y);
    const p = this.pointers.get(id);
    this.pointers.delete(id);
    return p && !p.dragged && p.hit && hit ? p.type : null;
  }
  cancel() { this.pointers.clear(); }
  get active() { return this.pointers.size > 0; }
}

export function initialState() {
  return { mode: 'ship', hover: false, selected: false, focus: false };
}
export function reduce(state, event) {
  switch (event.type) {
    case 'hover': return { ...state, hover: state.mode === 'ship' && event.value };
    case 'focus': return { ...state, focus: state.mode === 'ship' && event.value };
    case 'select': return { ...state, selected: true };
    case 'activate':
      if (state.mode !== 'ship') return state;
      if (event.pointer !== 'mouse' && !state.selected) return { ...state, selected: true };
      return { ...state, mode: 'archive', hover: false, focus: false, selected: false };
    case 'enter': return { ...state, mode: 'archive', hover: false, focus: false, selected: false };
    case 'back': return initialState();
    case 'escape': return state.mode === 'archive' ? initialState() : { ...state, selected: false, hover: false, focus: false };
    default: return state;
  }
}
export function cutawayOpen(state) {
  return state.mode === 'archive' || state.hover || state.selected || state.focus;
}
export function renderScale(width, height, deviceRatio, quality) {
  const pixels = quality === 'light' ? 800000 : 1600000;
  const ceiling = quality === 'light' ? 1 : 1.5;
  return Math.max(.1, Math.min(deviceRatio, ceiling, Math.sqrt(pixels / Math.max(1, width * height))));
}
