import test from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import sharp from 'sharp';
import { runWriting } from './writing.mjs';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const hash = data => createHash('sha256').update(data).digest('hex');
async function fixture(t) {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'kuhai-writing-')));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, 'authoring/templates'), { recursive: true });
  for (const name of ['note', 'technical']) await fs.copyFile(path.join(sourceRoot, 'authoring/templates', name + '.md'), path.join(root, 'authoring/templates', name + '.md'));
  await fs.mkdir(path.join(root, 'content/content/posts'), { recursive: true });
  await fs.mkdir(path.join(root, 'content/config'), { recursive: true });
  await fs.writeFile(path.join(root, 'content/config/site.yaml'), 'title: existing public site\n');
  await fs.writeFile(path.join(root, 'content/content/posts/existing.md'), '---\ntitle: Existing\npublished: 2026-10-22\ndraft: false\n---\nExisting public text.\n');
  return root;
}
async function lock(root) {
  await fs.mkdir(path.join(root, 'release-plan'), { recursive: true });
  await fs.writeFile(path.join(root, 'release-plan/.release.lock'), JSON.stringify({ token: 'fixture-owner', pid: process.pid }), { flag: 'wx' });
}
async function post(root, slug, body = 'This is a real test fixture body.', fields = '') {
  const folder = path.join(root, 'authoring-private', slug);
  await fs.mkdir(path.join(folder, 'images'), { recursive: true });
  await fs.writeFile(path.join(folder, 'post.md'), '---\ntitle: Fixture article\npublished: 2026-10-22\ndraft: true\n' + fields + '---\n\n' + body + '\n');
  return folder;
}
async function image(folder, name = 'figure.png', options = {}) {
  const output = path.join(folder, 'images', name);
  await fs.mkdir(path.dirname(output), { recursive: true });
  await sharp({ create: { width: options.width || 3, height: options.height || 2, channels: 3, background: '#123456' } }).png().toFile(output);
  return output;
}
async function tree(root) {
  const result = {};
  async function visit(dir) {
    for (const item of await fs.readdir(dir, { withFileTypes: true })) {
      const p = path.join(dir, item.name), key = path.relative(root, p).split(path.sep).join('/');
      result[key] = item.isDirectory() ? 'directory' : hash(await fs.readFile(p));
      if (item.isDirectory()) await visit(p);
    }
  }
  await visit(root); return result;
}
const call = (root, args, extras = {}) => runWriting(args, { root, ownerToken: 'fixture-owner', ...extras });

test('new creates only an isolated draft using Shanghai date and YAML-safe title', async t => {
  const root = await fixture(t), before = await tree(path.join(root, 'content'));
  const result = await call(root, ['new', 'my-note', '--title', '标题: "真实草稿"'], { now: new Date('2026-10-22T16:01:00Z') });
  assert.equal(result.passed, true); assert.equal(result.route, '/blog/posts/my-note/');
  const text = await fs.readFile(path.join(root, 'authoring-private/my-note/post.md'), 'utf8');
  assert.match(text, /published: 2026-10-23/); assert.match(text, /draft: true/);
  assert.deepEqual(await tree(path.join(root, 'content')), before);
  assert.equal((await call(root, ['check', 'my-note'])).passed, true);
  assert.equal((await call(root, ['new', 'my-note', '--title', 'Other'])).passed, false);
});
test('technical template is a draft and its placeholder cannot be published', async t => {
  const root = await fixture(t); await lock(root);
  const made = await call(root, ['new', 'technical-note', '--title', 'Technical note', '--template', 'technical']);
  assert.equal(made.passed, true);
  const result = await call(root, ['prepare-publish', 'technical-note']);
  assert.equal(result.passed, false); assert.ok(result.errors.some(e => e.code === 'TEMPLATE_UNFINISHED'));
  assert.deepEqual(Object.keys(await tree(path.join(root, 'content/content/posts'))), ['existing.md']);
});
test('unsafe slugs and duplicate or unsupported CLI options are rejected', async t => {
  const root = await fixture(t);
  for (const args of [['new', '../escape', '--title', 'x'], ['new', 'valid', '--title', 'x', '--title', 'y'], ['new', 'valid', '--title', 'x', '--template', 'other'], ['check', 'valid', '--out', '/tmp']]) assert.equal((await call(root, args)).passed, false);
});
test('check reads only referenced images and keeps production/private trees unchanged', async t => {
  const root = await fixture(t), folder = await post(root, 'with-image', '![A test diagram](images/figure.png "Caption")');
  await image(folder); await fs.writeFile(path.join(folder, 'images/unused.png'), 'invalid unreferenced image');
  const before = await tree(root), result = await call(root, ['check', 'with-image']);
  assert.equal(result.passed, true); assert.equal(result.mapped.length, 1); assert.equal(result.mapped[0].width, 3);
  assert.equal(result.sourceHashes.length, 2); assert.deepEqual(await tree(root), before);
});
test('check rejects missing images, blank alt, remote paths, traversal and format mismatch', async t => {
  const root = await fixture(t);
  const cases = [['missing', '![Description](images/missing.png)'], ['alt', '![](images/figure.png)'], ['remote', '![Description](https://example.test/private.png)'], ['escape', '![Description](images/%2e%2e/secret.png)'], ['mismatch', '![Description](images/figure.jpg)']];
  for (const [slug, body] of cases) {
    const folder = await post(root, slug, body); await image(folder, slug === 'mismatch' ? 'figure.jpg' : 'figure.png');
    assert.equal((await call(root, ['check', slug])).passed, false, slug);
  }
});
test('long screenshots produce warnings, not a publishing prohibition', async t => {
  const root = await fixture(t), folder = await post(root, 'long-image', '![A long screenshot](images/figure.png)');
  await image(folder, 'figure.png', { width: 2, height: 12001 });
  const result = await call(root, ['check', 'long-image']);
  assert.equal(result.passed, true); assert.ok(result.warnings.some(w => w.code === 'LARGE_DIMENSIONS'));
});
test('date mismatch, non-draft source and unsafe embeds are rejected', async t => {
  const root = await fixture(t);
  await post(root, 'wrong-date', 'Text', 'publishedAt: 2026-10-22T23:00:00Z\n');
  assert.equal((await call(root, ['check', 'wrong-date'])).passed, false);
  const folder = await post(root, 'not-draft');
  const p = path.join(folder, 'post.md'); await fs.writeFile(p, (await fs.readFile(p, 'utf8')).replace('draft: true', 'draft: false'));
  assert.equal((await call(root, ['check', 'not-draft'])).passed, false);
  await post(root, 'embedded', '<img src="images/figure.png">');
  assert.equal((await call(root, ['check', 'embedded'])).passed, false);
});
test('filesystem examples inside fenced code are not interpreted as resources', async t => {
  const root = await fixture(t); await post(root, 'code-example', '```md\n![example](images/missing.png)\n<!-- @include: private.txt -->\n```');
  assert.equal((await call(root, ['check', 'code-example'])).passed, true);
});

test('all supported code-tree directory import forms are refused without modifying private or public files', async t => {
  const root = await fixture(t);
  const forms = [
    '@[code-tree](/src/content)',
    '@[code-tree title="Example"](/src/content)',
    '[@code-tree](/src/content)',
    '[@code-tree title="Example"](/src/content)',
    String.raw`@\[code-tree\](/src/content)`,
    '::code-tree{dir="/src/content"}',
    "::code-tree{title='Example' dir='/src/content'}",
    '::code-tree{dir=/src/content}',
    ':::code-tree{dir="/src/content"}\n:::',
    ':::code-tree{dir="/src/content"}\n\nExisting child text.\n\n:::',
    '> ::code-tree{dir="/src/content"}',
    '- @[code-tree](/src/content)',
  ];
  for (const [index, body] of forms.entries()) {
    const slug = 'include-' + index; await post(root, slug, body);
    const before = await tree(root), result = await call(root, ['check', slug]);
    assert.equal(result.passed, false, body);
    assert.ok(result.errors.some(e => e.code === 'UNSUPPORTED_INCLUDE'), body);
    assert.deepEqual(await tree(root), before);
  }
});

test('code-tree imports cannot reach publication or preview even with the current lock', async t => {
  const root = await fixture(t); await lock(root);
  await post(root, 'include-at-write', '::code-tree{dir="/src/content"}');
  const before = await tree(root);
  for (const args of [['prepare-publish', 'include-at-write'], ['export-preview', 'include-at-write', '--out', path.join(root, 'preview-work/refused/content')]]) {
    const result = await call(root, args);
    assert.equal(result.passed, false);
    assert.ok(result.errors.some(e => e.code === 'UNSUPPORTED_INCLUDE'));
    assert.deepEqual(await tree(root), before);
  }
});

test('fenced and inline code-tree syntax examples and manually authored code trees remain usable', async t => {
  const root = await fixture(t);
  const syntax = ['@[code-tree](/src/content)', '[@code-tree](/src/content)', '::code-tree{dir="/src/content"}', ':::code-tree{dir="/src/content"}\n:::'];
  const body = syntax.map(value => '```md\n' + value + '\n```').join('\n\n')
    + '\n\n' + syntax.slice(0, 3).map(value => '`' + value + '`').join('\n\n')
    + '\n\n:::code-tree{title="Manually authored example"}\n\n```js title="example.js"\nconsole.log("Example");\n```\n\n:::';
  await post(root, 'literal-examples', body);
  const result = await call(root, ['check', 'literal-examples']);
  assert.equal(result.passed, true, JSON.stringify(result.errors));
  assert.equal(result.sourceHashes.length, 1);
});
test('prepare-publish requires the current shared lock owner', async t => {
  const root = await fixture(t); await post(root, 'locked');
  const before = await tree(path.join(root, 'content'));
  assert.equal((await call(root, ['prepare-publish', 'locked'])).passed, false);
  await lock(root);
  assert.equal((await call(root, ['prepare-publish', 'locked'], { ownerToken: 'wrong-owner' })).passed, false);
  assert.deepEqual(await tree(path.join(root, 'content')), before);
});
test('prepare-publish copies only referenced images, rewrites inline/cover/reference URLs, and preserves private files', async t => {
  const root = await fixture(t); await lock(root);
  const folder = await post(root, 'publishable', '![Diagram](images/figure.png "Caption")\n\n![Reference][diagram]\n\n[diagram]: images/figure.png\n\n```md\n![untouched](images/not-used.png)\n```', 'image: images/figure.png\n');
  await image(folder); await image(folder, 'unused.png');
  const privateBefore = await tree(folder), result = await call(root, ['prepare-publish', 'publishable']);
  assert.equal(result.passed, true, JSON.stringify(result.errors));
  assert.equal(result.copied.filter(x => x.kind === 'referenced-image').length, 1);
  const text = await fs.readFile(path.join(root, 'content/content/posts/publishable.md'), 'utf8');
  assert.match(text, /draft: false/); assert.match(text, /image: \/blog\/images\/posts\/publishable\/figure.png/);
  assert.match(text, /\[diagram\]: \/blog\/images\/posts\/publishable\/figure.png/); assert.match(text, /images\/not-used.png/);
  assert.deepEqual(await tree(folder), privateBefore);
  assert.equal((await call(root, ['prepare-publish', 'publishable'])).passed, false);
});
test('existing image destination is rejected before writing an article', async t => {
  const root = await fixture(t); await lock(root); await post(root, 'collision');
  await fs.mkdir(path.join(root, 'content/public/images/posts/collision'), { recursive: true });
  const before = await tree(path.join(root, 'content'));
  assert.equal((await call(root, ['prepare-publish', 'collision'])).passed, false);
  assert.deepEqual(await tree(path.join(root, 'content')), before);
});
test('check rejects mdx, directory, alias and permalink route collisions', async t => {
  const root = await fixture(t);
  for (const slug of ['same-mdx', 'same-dir', 'same-alias', 'same-permalink']) await post(root, slug);
  const posts = path.join(root, 'content/content/posts');
  const header = '---\ntitle: Public\npublished: 2026-10-22\ndraft: false\n';
  await fs.writeFile(path.join(posts, 'same-mdx.mdx'), header + '---\nPublic body');
  await fs.mkdir(path.join(posts, 'same-dir'));
  await fs.writeFile(path.join(posts, 'alias-owner.md'), header + 'alias: same-alias\n---\nPublic body');
  await fs.writeFile(path.join(posts, 'permalink-owner.md'), header + 'permalink: /posts/same-permalink/\n---\nPublic body');
  for (const slug of ['same-mdx', 'same-dir', 'same-alias', 'same-permalink']) {
    const result = await call(root, ['check', slug]);
    assert.equal(result.passed, false); assert.ok(result.errors.some(e => e.code === 'DESTINATION_EXISTS'));
  }
});
test('preview clones site config and inserts only the chosen draft without changing canonical content', async t => {
  const root = await fixture(t); await lock(root);
  const folder = await post(root, 'preview-one', '![Preview picture](images/figure.png)'); await image(folder); await image(folder, 'unused.png');
  await post(root, 'unselected-private', 'Must never appear in preview-one');
  const before = await tree(path.join(root, 'content')), privateBefore = await tree(path.join(root, 'authoring-private'));
  const out = path.join(root, 'preview-work/test-version/content'), result = await call(root, ['export-preview', 'preview-one', '--out', out]);
  assert.equal(result.passed, true, JSON.stringify(result.errors)); assert.equal(result.outputContent, out);
  assert.equal(await fs.readFile(path.join(out, 'config/site.yaml'), 'utf8'), 'title: existing public site\n');
  const exported = await tree(out); assert.ok(exported['content/posts/preview-one.md']); assert.ok(exported['content/posts/existing.md']);
  assert.ok(!Object.keys(exported).some(p => /unselected-private|unused.png/.test(p)));
  assert.deepEqual(await tree(path.join(root, 'content')), before); assert.deepEqual(await tree(path.join(root, 'authoring-private')), privateBefore);
  assert.equal((await call(root, ['export-preview', 'preview-one', '--out', out])).passed, false);
});
test('preview refuses external, relative and malformed target paths', async t => {
  const root = await fixture(t); await lock(root); await post(root, 'preview-path');
  for (const out of ['relative/content', path.join(root, 'elsewhere/content'), path.join(root, 'preview-work/a/nested/content'), path.join(root, 'preview-work/-bad/content')]) assert.equal((await call(root, ['export-preview', 'preview-path', '--out', out])).passed, false);
  assert.ok(!Object.keys(await tree(root)).some(p => p.startsWith('preview-work/')));
});
test('linked private image directory is rejected without reading its target', async t => {
  const root = await fixture(t), folder = await post(root, 'linked-image', '![Description](images/linked/figure.png)');
  const target = path.join(root, 'outside-images'); await fs.mkdir(target);
  const link = path.join(folder, 'images/linked');
  try { await fs.symlink(target, link, process.platform === 'win32' ? 'junction' : 'dir'); } catch (e) { if (['EPERM', 'EACCES'].includes(e.code)) return t.skip('Creating the fixture link is not permitted'); throw e; }
  try {
    const result = await call(root, ['check', 'linked-image']);
    assert.equal(result.passed, false); assert.ok(result.errors.some(e => /links|symlinks/.test(e.message)));
  } finally { await fs.unlink(link); }
});
