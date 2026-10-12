import test from 'node:test';
import assert from 'node:assert/strict';
import { GestureTracker, initialState, reduce, cutawayOpen, renderScale } from '../src/interaction.mjs';

test('dragging across a compartment does not activate it, including returning to origin', () => {
  const g = new GestureTracker();
  g.down(1, 0, 0, true); g.move(1, 20, 0); g.move(1, 0, 0);
  assert.equal(g.up(1, 0, 0, true), null);
  g.down(1, 0, 0, false); assert.equal(g.up(1, 1, 0, true), null);
  g.down(1, 0, 0, true); assert.equal(g.up(1, 1, 0, false), null);
  g.down(1, 0, 0, true); assert.equal(g.up(1, 1, 0, true), 'mouse');
});
test('neither finger of a pinch can activate the compartment', () => {
  const g = new GestureTracker();
  g.down(1, 0, 0, true, 'touch'); g.down(2, 10, 0, true, 'touch');
  assert.equal(g.up(2, 10, 0, true), null);
  assert.equal(g.up(1, 0, 0, true), null);
  g.down(3, 0, 0, true, 'touch'); g.cancel();
  assert.equal(g.up(3, 0, 0, true), null);
});
test('touch and keyboard select before entering; mouse click enters directly', () => {
  for (const pointer of ['touch', 'keyboard']) {
    let s = reduce(initialState(), { type: 'activate', pointer });
    assert.equal(s.mode, 'ship'); assert.equal(cutawayOpen(s), true);
    s = reduce(s, { type: 'activate', pointer }); assert.equal(s.mode, 'archive');
    assert.deepEqual(reduce(s, { type: 'back' }), initialState());
  }
  assert.equal(reduce(initialState(), { type: 'activate', pointer: 'mouse' }).mode, 'archive');
});
test('hover is a visibility state and never creates or changes transforms', () => {
  const source = Object.freeze(initialState());
  let s = reduce(source, { type: 'hover', value: true });
  assert.equal(cutawayOpen(s), true); assert.equal(source.hover, false);
  assert.deepEqual(Object.keys(s).sort(), ['focus', 'hover', 'mode', 'selected']);
  s = reduce(s, { type: 'hover', value: false }); assert.equal(cutawayOpen(s), false);
  s = reduce(s, { type: 'select' });
  s = reduce(s, { type: 'hover', value: false }); assert.equal(cutawayOpen(s), true);
  s = reduce(s, { type: 'escape' }); assert.equal(cutawayOpen(s), false);
});
test('pixel limits hold on high-DPI phones and 4K screens', () => {
  for (const [w, h, dpr] of [[390,844,3],[1920,1080,2],[3840,2160,2]]) {
    for (const quality of ['standard','light']) {
      const scale = renderScale(w,h,dpr,quality);
      assert.ok(w * h * scale * scale <= (quality === 'light' ? 800000 : 1600000) + 1);
    }
  }
});
