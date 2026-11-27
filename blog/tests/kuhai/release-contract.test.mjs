import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import { renderFilingLinks } from '../../scripts/kuhai/configure.mjs';
import { resolveFontOptions } from '../../src/utils/font-options.ts';

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8');
const content = (path) => readFileSync(new URL(`../../../content/${path}`, import.meta.url), 'utf8');

test('pending filing text never appears in the generated footer', () => {
  const html = renderFilingLinks({ icp: { approved: false, displayText: 'application-only', url: '' }, publicSecurity: { approved: false } });
  assert.equal(html.includes('<a'), false);
  assert.equal(html.includes('application-only'), false);
});
test('issued filings require complete records and escape display text', () => {
  assert.throws(() => renderFilingLinks({ icp: { approved: true, displayText: '', url: 'https://beian.miit.gov.cn/' } }));
  assert.throws(() => renderFilingLinks({ icp: { approved: true, displayText: 'Issued', url: 'javascript:alert(1)' } }));
  const html = renderFilingLinks({ icp: { approved: true, displayText: '<issued & verified>', url: 'https://beian.miit.gov.cn/' } });
  assert.match(html, /&lt;issued &amp; verified&gt;/);
  assert.equal(html.includes('<issued'), false);
});
test('owner content is explicitly local and only the approved site introduction is published', () => {
  const manifest = JSON.parse(read('shirone.content.json'));
  assert.deepEqual(manifest.source, { type: 'path', path: '../content' });
  for (const name of ['moments', 'series']) {
    const files = readdirSync(new URL(`../../../content/content/${name}/`, import.meta.url));
    assert.deepEqual(files, ['.keep']);
  }
  const posts = readdirSync(new URL('../../../content/content/posts/', import.meta.url));
  assert.deepEqual(posts.sort(), ['.keep', 'welcome-to-archive.md']);
  assert.match(content('content/posts/welcome-to-archive.md'), /published: 2026-10-22/);
  assert.match(content('content/spec/about.md'), /本站说明/);
});
test('empty collections retain a real homepage and readable empty state', () => {
  assert.match(read('src/pages/[...page].astro'), /if \(allBlogPosts.length === 0\)/);
  assert.match(read('src/pages/[...page].astro'), /params: \{ page: undefined \}/);
  assert.match(read('src/components/organisms/PostPage.astro'), /blogEmptyTitle/);
  assert.match(read('src/components/organisms/PostPage.astro'), /blogEmptyDescription/);
});
test('return-to-ship is a same-tab document navigation at the site root', () => {
  const navigation = JSON.parse(content('config/nav-bar.yaml'));
  const ship = navigation.links.find((link) => link.pageKey === 'flagship');
  assert.equal(ship.url, '/');
  assert.equal(ship.fullReload, true);
  assert.notEqual(ship.external, true);
  assert.match(read('src/components/organisms/TopAppBar.astro'), /data-no-swup=\{link.fullReload/);
  assert.match(read('src/components/organisms/SiteNavigationDrawer.svelte'), /data-no-swup=\{item.fullReload/);
  assert.match(read('src/config/integrationsConfig.ts'), /a\[data-no-swup\]/);
});
test('new user-facing copy is supplied in every supported locale', () => {
  const locales = readdirSync(new URL('../../src/i18n/languages/', import.meta.url)).filter((name) => name.endsWith('.ts'));
  assert.equal(locales.length, 10);
  for (const locale of locales) {
    const source = read(`src/i18n/languages/${locale}`);
    for (const key of ['blogEmptyTitle', 'blogEmptyDescription', 'navigationMenuLabel', 'navigationMainLabel', 'feedWebReaders', 'feedAppReaders']) {
      assert.match(source, new RegExp(`\\[Key\\.${key}\\]:\\s*"[^"\\n]+"`));
    }
  }
});
test('feed and robots endpoints resolve through the blog-base helper', () => {
  assert.match(read('src/pages/atom.xml.ts'), /new URL\(url\("atom.xml"\), site\)/);
  assert.match(read('src/pages/rss.xml.ts'), /new URL\(url\("\/"\), site\)/);
  assert.match(read('src/pages/robots.txt.ts'), /url\("sitemap-index.xml"\)/);
  assert.match(read('src/layouts/Layout.astro'), /toAbsoluteUrl\("rss.xml", Astro.site\)/);
});
test('font configuration resolves exclusively to existing local assets', () => {
  const config = JSON.parse(content('config/font.yaml'));
  const resolved = resolveFontOptions(config);
  assert.equal(resolved.mode, 'custom');
  assert.equal(resolved.subsetting.allowRemoteText, false);
  for (const role of ['body', 'cjk', 'mono']) {
    assert.ok(resolved.roles[role].variants.length > 0);
    for (const variant of resolved.roles[role].variants) {
      assert.equal(variant.source, 'local');
      const bytes = readFileSync(new URL(`../../${variant.file}`, import.meta.url));
      assert.ok(bytes.length > 0);
      if (variant.file.endsWith('.woff2')) assert.equal(bytes.toString('ascii', 0, 4), 'wOF2');
    }
  }
});
