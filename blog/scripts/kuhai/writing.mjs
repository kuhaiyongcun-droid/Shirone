// Local authoring only. Private drafts are never mounted into the production blog.
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { parseDocument, stringify } from 'yaml';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkDirective from 'remark-directive';
import sharp from 'sharp';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const VERSION = /^[a-z0-9][a-z0-9_-]{0,47}$/;
const IMAGE_TYPES = new Map([['.png', 'png'], ['.jpg', 'jpeg'], ['.jpeg', 'jpeg'], ['.webp', 'webp'], ['.avif', 'heif'], ['.gif', 'gif']]);
const TEMPLATE_MARKER = '<!-- AUTHORING_TEMPLATE: replace this placeholder before publication -->';
const DENIED = /^(?:\.env(?:\..*)?|\.npmrc|\.git|credentials|id_rsa|id_ed25519)$/i;
const digest = data => createHash('sha256').update(data).digest('hex');
const rel = (root, filename) => path.relative(root, filename).split(path.sep).join('/');
const inside = (root, filename) => filename === root || (!path.relative(root, filename).startsWith('..' + path.sep) && path.relative(root, filename) !== '..' && !path.isAbsolute(path.relative(root, filename)));
function fail(message) { throw new Error(message); }
function issue(list, code, message, file) { list.push({ code, message, ...(file ? { file } : {}) }); }
async function exists(filename) { try { await fs.lstat(filename); return true; } catch (e) { if (e.code === 'ENOENT') return false; throw e; } }

async function safePath(root, filename, { required = true, directory = false } = {}) {
  const full = path.resolve(filename);
  if (!inside(root, full)) fail('Path escapes the authoring workspace');
  const parts = path.relative(root, full).split(path.sep).filter(Boolean);
  let current = root;
  for (const part of ['', ...parts]) {
    if (part) current = path.join(current, part);
    let stat;
    try { stat = await fs.lstat(current); } catch (e) {
      if (e.code === 'ENOENT' && !required) return full;
      throw e;
    }
    if (stat.isSymbolicLink()) fail('Directory links and file symlinks are not allowed: ' + rel(root, current));
    const actual = await fs.realpath(current);
    if (path.relative(actual, current) !== '') fail('Aliased authoring paths are not allowed: ' + rel(root, current));
    if (current !== full && !stat.isDirectory()) fail('Non-directory path ancestor');
    if (current === full && (directory ? !stat.isDirectory() : !stat.isFile())) fail('Unexpected file type: ' + rel(root, current));
  }
  return full;
}

async function readSafe(root, filename) {
  await safePath(root, filename);
  const data = await fs.readFile(filename);
  return { data, record: { path: rel(root, filename), bytes: data.length, sha256: digest(data) } };
}

async function requireReleaseOwner(root, token) {
  const lock = await readSafe(root, path.join(root, 'release-plan/.release.lock')).catch(() => fail('Use the Python authoring/preview entry point: an owned release lock is required'));
  let value;
  try { value = JSON.parse(lock.data.toString('utf8')); } catch { fail('Release lock is invalid; no files were written'); }
  if (!token || value.token !== token) fail('Another process owns the release lock; use the Python entry point');
}

function parseArgs(argv) {
  const [command, slug, ...rest] = argv;
  if (!['new', 'check', 'prepare-publish', 'export-preview'].includes(command) || !SLUG.test(slug || '')) fail('Usage: new|check|prepare-publish|export-preview <lowercase-hyphenated-slug> [options]');
  const opts = {};
  for (let i = 0; i < rest.length; i += 2) {
    const key = rest[i], value = rest[i + 1];
    if (!['--title', '--template', '--out'].includes(key) || value === undefined || Object.hasOwn(opts, key)) fail('Unknown, missing or duplicate option');
    opts[key] = value;
  }
  const allowed = command === 'new' ? ['--title', '--template'] : command === 'export-preview' ? ['--out'] : [];
  if (Object.keys(opts).some(key => !allowed.includes(key))) fail('Option is not supported by this command');
  return { command, slug, opts };
}

function parsePost(text) {
  const match = /^(?:\uFEFF)?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/.exec(text);
  if (!match) fail('post.md must begin with YAML frontmatter');
  const doc = parseDocument(match[1], { uniqueKeys: true, strict: true });
  if (doc.errors.length) fail('Invalid YAML frontmatter: ' + doc.errors.map(e => e.message).join('; '));
  const data = doc.toJS({ maxAliasCount: 0 });
  if (!data || typeof data !== 'object' || Array.isArray(data)) fail('Frontmatter must be an object');
  return { data, body: match[2] };
}
function calendarDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
}
function shanghaiDate(now) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}
function imagePath(value) {
  if (typeof value !== 'string') fail('Image path must be a string');
  let decoded;
  try { decoded = decodeURIComponent(value); } catch { fail('Invalid encoded image path'); }
  if (!decoded.startsWith('images/') || /[\\:?"<>|#%\u0000-\u001f\u007f]/.test(decoded)) fail('Use a local images/<filename> path; remote, absolute and encoded traversal paths are not allowed');
  const parts = decoded.split('/');
  if (parts.some(p => !p || p === '.' || p === '..' || /[. ]$/.test(p) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(p) || DENIED.test(p))) fail('Unsafe image path');
  if (!IMAGE_TYPES.has(path.posix.extname(decoded).toLowerCase())) fail('Supported article image types: PNG, JPEG, WebP, AVIF and GIF; SVG and other formats require a separate review');
  return decoded;
}
function walk(node, visit) { visit(node); for (const child of node.children || []) walk(child, visit); }
function importsCodeTreeDirectory(node) {
  // Mirror the importing AST forms in src/plugins/markdown/code/remark-code-tree.mjs.
  // Never run that transformer here: it recursively reads the supplied directory.
  if (['leafDirective', 'containerDirective'].includes(node.type) && node.name === 'code-tree') return Object.hasOwn(node.attributes || {}, 'dir');
  if (node.type !== 'paragraph') return false;
  const children = node.children || [];
  const linkText = link => (link.children || []).map(child => child.value || '').join('').trim();
  if (children.length === 2 && children[0].type === 'text' && children[0].value.trim() === '@' && children[1].type === 'link') return linkText(children[1]).startsWith('code-tree');
  if (children.length === 1 && children[0].type === 'link') return linkText(children[0]).startsWith('@code-tree');
  return children.length === 1 && children[0].type === 'text' && /^@\[code-tree(?:\s+[^\]]*)?\]\([^)]+\)$/.test(children[0].value.trim());
}
function markdownImage(url, alt, title) {
  const label = String(alt || '').replace(/\\/g, '\\\\').replace(/\[/g, '\\[').replace(/\]/g, '\\]').replace(/\r?\n/g, ' ');
  const caption = title ? ' "' + title.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\r?\n/g, ' ') + '"' : '';
  return `![${label}](${url}${caption})`;
}

async function findRouteConflicts(root, slug) {
  const base = path.join(root, 'content/content/posts'), conflicts = [];
  await safePath(root, base, { directory: true });
  async function visit(dir) {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      const filename = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) fail('Published posts cannot contain linked paths');
      if (dir === base && entry.name.toLowerCase() === slug && entry.isDirectory()) conflicts.push(rel(root, filename));
      if (entry.isDirectory()) { await safePath(root, filename, { directory: true }); await visit(filename); continue; }
      if (!/\.mdx?$/i.test(entry.name)) continue;
      const source = await readSafe(root, filename), { data } = parsePost(source.data.toString('utf8'));
      const id = path.relative(base, filename).split(path.sep).join('/').replace(/\.mdx?$/i, '').toLowerCase();
      const clean = value => typeof value === 'string' ? value.trim().replace(/^\/+|\/+$/g, '') : '';
      const permalink = clean(data.permalink), alias = clean(data.alias).replace(/^posts\//, '');
      if (id === slug || permalink === 'posts/' + slug || (!permalink && alias === slug)) conflicts.push(source.record.path);
    }
  }
  await visit(base);
  if (await exists(path.join(root, 'content/public/images/posts', slug))) conflicts.push('content/public/images/posts/' + slug);
  return [...new Set(conflicts)];
}

async function inspect(root, slug, report) {
  const folder = path.join(root, 'authoring-private', slug);
  const post = await readSafe(root, path.join(folder, 'post.md'));
  report.sourceHashes.push(post.record);
  const parsed = parsePost(post.data.toString('utf8'));
  const { data, body } = parsed;
  report.title = typeof data.title === 'string' ? data.title : '';
  for (const filename of await findRouteConflicts(root, slug)) issue(report.errors, 'DESTINATION_EXISTS', 'An existing public article, route or image directory owns this slug; this CLI does not overwrite published articles', filename);
  if (!report.title.trim()) issue(report.errors, 'TITLE_REQUIRED', 'A non-empty title is required');
  if (!calendarDate(data.published)) issue(report.errors, 'PUBLISHED_INVALID', 'published must be a real YYYY-MM-DD calendar date');
  if (data.draft !== true) issue(report.errors, 'PRIVATE_DRAFT_REQUIRED', 'Private post.md must keep draft: true; publication changes only the exported copy');
  for (const key of ['description', 'image', 'category', 'lang', 'series']) if (data[key] != null && typeof data[key] !== 'string') issue(report.errors, 'FIELD_TYPE', key + ' must be a string');
  for (const key of ['pinned', 'comment', 'encrypted', 'hideHomeContent']) if (data[key] !== undefined && typeof data[key] !== 'boolean') issue(report.errors, 'FIELD_TYPE', key + ' must be a boolean');
  if (data.tags !== undefined && (!Array.isArray(data.tags) || data.tags.some(x => typeof x !== 'string' || !x.trim()))) issue(report.errors, 'TAGS_INVALID', 'tags must be a list of non-empty strings');
  if (data.updated !== undefined && !calendarDate(data.updated)) issue(report.errors, 'UPDATED_INVALID', 'updated must be a real YYYY-MM-DD date');
  for (const [instant, day] of [['publishedAt', 'published'], ['updatedAt', 'updated']]) if (data[instant] !== undefined) {
    const value = data[instant];
    if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value)) || shanghaiDate(new Date(value)) !== data[day]) issue(report.errors, 'INSTANT_INVALID', instant + ' must include an offset and match ' + day + ' in Asia/Shanghai');
  }
  if (data.alias || data.permalink) issue(report.errors, 'ROUTE_OVERRIDE', 'This writing workflow reserves /blog/posts/<slug>/; omit alias/permalink');
  if (data.password !== undefined || data.encrypted === true) issue(report.errors, 'PASSWORD_UNSUPPORTED', 'Do not put passwords in article frontmatter; keep private content in authoring-private');
  if (!body.trim()) issue(report.errors, 'EMPTY_BODY', 'Article body is empty');
  if (body.includes(TEMPLATE_MARKER)) issue(report.warnings, 'TEMPLATE_PLACEHOLDER', 'Replace the template placeholder and remove its marker before publication');
  const tree = unified().use(remarkParse).use(remarkDirective).parse(body);
  const definitions = new Map();
  walk(tree, n => { if (n.type === 'definition') definitions.set(n.identifier, n); });
  const usages = [], replacements = [], replacedDefinitions = new Set();
  if (data.image) usages.push({ value: data.image, alt: report.title, cover: true });
  walk(tree, node => {
    if (node.type === 'image') usages.push({ value: node.url, alt: node.alt, node });
    if (node.type === 'imageReference') {
      const definition = definitions.get(node.identifier);
      if (!definition) issue(report.errors, 'IMAGE_REFERENCE_MISSING', 'Missing image reference definition: ' + node.identifier);
      else usages.push({ value: definition.url, alt: node.alt, node, definition });
    }
    if (node.type === 'html' && /<(?:img|picture|source|svg|video|audio|iframe|script|style)\b|@include\s*:/i.test(node.value)) issue(report.errors, 'UNSUPPORTED_EMBED', 'Use Markdown images; HTML media, scripts/styles and filesystem includes are not supported by this checked workflow');
    if (node.type === 'link' && /^(?:images\/|(?:\.\.\/)+|file:)/i.test(node.url)) issue(report.errors, 'UNSUPPORTED_FILE_LINK', 'Local attachment links require separate review; use Markdown image syntax for article images');
    if (importsCodeTreeDirectory(node)) issue(report.errors, 'UNSUPPORTED_INCLUDE', 'Filesystem code-tree includes are not supported by this checked workflow; keep syntax examples inside fenced or inline code');
  });
  const images = new Map();
  for (const usage of usages) {
    let relative;
    try { relative = imagePath(usage.value); } catch (e) { issue(report.errors, 'IMAGE_PATH', e.message, String(usage.value)); continue; }
    const alt = String(usage.alt || '').replace(/(?:^|\s)w-\d+%\b/g, '').trim();
    if (!alt) issue(report.errors, 'IMAGE_ALT_REQUIRED', 'Describe the image with meaningful alt text', relative);
    const url = '/blog/images/posts/' + slug + '/' + relative.slice(7).split('/').map(encodeURIComponent).join('/');
    if (!images.has(relative)) {
      try {
        const file = await readSafe(root, path.join(folder, ...relative.split('/')));
        const meta = await sharp(file.data).metadata();
        const expected = IMAGE_TYPES.get(path.posix.extname(relative).toLowerCase());
        if (meta.format !== expected || !meta.width || !meta.height) fail('Image signature/format differs from its extension or its dimensions are unavailable');
        const metadata = { width: meta.width, height: meta.height, format: meta.format, pages: meta.pages || 1, hasExif: !!meta.exif };
        report.sourceHashes.push(file.record);
        images.set(relative, { ...file, relative, url, metadata });
        report.mapped.push({ source: file.record.path, url, bytes: file.record.bytes, ...metadata });
        if (file.data.length > 2 * 1024 * 1024) issue(report.warnings, 'LARGE_IMAGE', 'Image exceeds 2 MiB; consider a smaller web copy. No automatic conversion is performed', relative);
        if (meta.width > 4096 || meta.height > 12000) issue(report.warnings, 'LARGE_DIMENSIONS', 'Large dimensions; review mobile reading and download size. Long images remain allowed', relative);
        if (meta.exif) issue(report.warnings, 'EXIF_PRESENT', 'Image contains EXIF metadata; review it before publication', relative);
        if ((meta.pages || 1) > 1) issue(report.warnings, 'ANIMATED_IMAGE', 'Animated image; review motion and transfer size', relative);
      } catch (e) { issue(report.errors, 'IMAGE_FILE', e.message, relative); }
    }
    if (usage.cover) parsed.data.image = url;
    else if (usage.definition) {
      const d = usage.definition;
      if (!replacedDefinitions.has(d)) {
        const title = d.title ? ' ' + JSON.stringify(d.title) : '';
        replacements.push({ start: d.position.start.offset, end: d.position.end.offset, text: `[${d.label || d.identifier}]: ${url}${title}` });
        replacedDefinitions.add(d);
      }
    } else replacements.push({ start: usage.node.position.start.offset, end: usage.node.position.end.offset, text: markdownImage(url, usage.node.alt, usage.node.title) });
  }
  let outputBody = body;
  for (const r of replacements.sort((a, b) => b.start - a.start)) outputBody = outputBody.slice(0, r.start) + r.text + outputBody.slice(r.end);
  return { folder, post, data: parsed.data, outputBody, images: [...images.values()] };
}

async function checkUnchanged(root, records) {
  for (const record of records) {
    const current = await readSafe(root, path.join(root, ...record.path.split('/')));
    if (current.record.sha256 !== record.sha256 || current.record.bytes !== record.bytes) fail('Source changed during the operation: ' + record.path);
  }
}
async function copyContentPlan(root) {
  const base = path.join(root, 'content'), files = [];
  await safePath(root, base, { directory: true });
  async function visit(dir) {
    for (const entry of (await fs.readdir(dir, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      if (DENIED.test(entry.name) || /\.(?:pem|key|p12|pfx)$/i.test(entry.name)) fail('Unsupported private/config file in published content tree: ' + entry.name);
      const filename = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) fail('Content clone refuses directory links and symlinks');
      if (entry.isDirectory()) { await safePath(root, filename, { directory: true }); await visit(filename); }
      else { const file = await readSafe(root, filename); files.push({ ...file, relative: path.relative(base, filename) }); }
    }
  }
  await visit(base); return files;
}

export async function runWriting(argv, { root = ROOT, now = new Date(), ownerToken = process.env.KUHAI_RELEASE_OWNER } = {}) {
  const report = { passed: false, command: argv[0] || '', slug: argv[1] || '', title: '', route: '', sourceHashes: [], errors: [], warnings: [], copied: [], mapped: [], outputs: [] };
  try {
    root = path.resolve(root);
    await safePath(root, root, { directory: true });
    const { command, slug, opts } = parseArgs(argv);
    report.command = command; report.slug = slug; report.route = '/blog/posts/' + slug + '/';
    const folder = path.join(root, 'authoring-private', slug);
    if (command === 'new') {
      const title = opts['--title']?.trim(), template = opts['--template'] || 'note';
      if (!title || /[\u0000-\u001f]/.test(title)) fail('A non-empty single-line --title is required');
      if (!['note', 'technical'].includes(template)) fail('--template must be note or technical');
      await safePath(root, folder, { required: false, directory: true });
      if (await exists(folder)) fail('Draft directory already exists; refusing to overwrite it');
      const source = await readSafe(root, path.join(root, 'authoring/templates', template + '.md'));
      const data = { title, published: shanghaiDate(now), description: '', image: '', tags: [], category: '', draft: true, comment: false };
      const text = '---\n' + stringify(data) + '---\n\n' + source.data.toString('utf8');
      await fs.mkdir(folder, { recursive: true }); await fs.mkdir(path.join(folder, 'images'));
      const output = path.join(folder, 'post.md'); await fs.writeFile(output, text, { flag: 'wx' });
      report.title = title; report.outputs.push(rel(root, output)); report.sourceHashes.push((await readSafe(root, output)).record);
      report.passed = true; return report;
    }
    const draft = await inspect(root, slug, report);
    if (command === 'check') { report.passed = report.errors.length === 0; return report; }
    if (command === 'prepare-publish' && report.warnings.some(w => w.code === 'TEMPLATE_PLACEHOLDER')) issue(report.errors, 'TEMPLATE_UNFINISHED', 'The generated placeholder must be replaced before prepare-publish');
    if (report.errors.length) return report;
    await requireReleaseOwner(root, ownerToken);
    let destination = path.join(root, 'content'), clone = [];
    if (command === 'export-preview') {
      const out = opts['--out'];
      if (!out || !path.isAbsolute(out)) fail('--out must be an absolute new preview-work/<version>/content path');
      destination = path.resolve(out);
      const parts = rel(root, destination).split('/');
      if (parts.length !== 3 || parts[0] !== 'preview-work' || !VERSION.test(parts[1]) || parts[2] !== 'content') fail('Preview output must be ROOT/preview-work/<version>/content');
      await safePath(root, destination, { required: false, directory: true });
      if (await exists(destination)) fail('Preview content directory already exists; choose a new version');
      clone = await copyContentPlan(root);
    } else await safePath(root, destination, { directory: true });
    const article = path.join(destination, 'content/posts', slug + '.md');
    const pictures = path.join(destination, 'public/images/posts', slug);
    await safePath(root, article, { required: false }); await safePath(root, pictures, { required: false, directory: true });
    if (await exists(article) || await exists(pictures) || clone.some(f => f.relative === path.join('content/posts', slug + '.md') || f.relative.startsWith(path.join('public/images/posts', slug) + path.sep))) fail('An article or image destination for this slug already exists; refusing to overwrite');
    await checkUnchanged(root, report.sourceHashes);
    await checkUnchanged(root, clone.map(f => f.record));
    await requireReleaseOwner(root, ownerToken);
    await fs.mkdir(destination, { recursive: true });
    for (const file of clone) {
      const output = path.join(destination, file.relative);
      await fs.mkdir(path.dirname(output), { recursive: true }); await fs.writeFile(output, file.data, { flag: 'wx' });
      report.copied.push({ source: file.record.path, output: rel(root, output), bytes: file.record.bytes, sha256: file.record.sha256, kind: 'existing-content' });
    }
    for (const image of draft.images) {
      const output = path.join(pictures, ...image.relative.slice(7).split('/'));
      await fs.mkdir(path.dirname(output), { recursive: true }); await fs.writeFile(output, image.data, { flag: 'wx' });
      report.copied.push({ source: image.record.path, output: rel(root, output), bytes: image.record.bytes, sha256: image.record.sha256, kind: 'referenced-image' });
      report.outputs.push(rel(root, output));
    }
    const articleText = '---\n' + stringify({ ...draft.data, draft: false }) + '---\n\n' + draft.outputBody;
    await fs.mkdir(path.dirname(article), { recursive: true }); await fs.writeFile(article, articleText, { flag: 'wx' });
    report.copied.push({ source: draft.post.record.path, output: rel(root, article), bytes: Buffer.byteLength(articleText), sha256: digest(articleText), kind: 'article-with-public-paths' });
    report.outputs.push(rel(root, article)); report.outputContent = destination;
    report.passed = true; return report;
  } catch (e) { issue(report.errors, 'AUTHORING_STOPPED', e.message); return report; }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await runWriting(process.argv.slice(2));
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.passed ? 0 : 1;
}
