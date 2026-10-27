/** Generate public blog configuration from the shared release/site.json. No credentials or network. */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateFilingRecord } from '../../../scripts/filing.mjs';

const releaseRoot = new URL('../../../', import.meta.url);
const contentConfig = new URL('content/config/', releaseRoot);
const escapeHtml = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');

function publicHttps(value, field) {
  const parsed = new URL(value);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error(`${field} must be a public HTTPS URL without credentials`);
  return parsed;
}

export function renderFilingLinks(filing = {}) {
  const links = [];
  for (const [name, item] of Object.entries(filing)) {
    if (!['icp', 'publicSecurity'].includes(name)) continue;
    const approved = validateFilingRecord(name, item);
    if (!approved) continue;
    const address = approved.url;
    let image = '';
    if (name === 'publicSecurity') {
      image = `<img src="${escapeHtml(approved.iconPath)}" alt="" width="20" height="20" loading="lazy" /> `;
    }
    links.push(`<a href="${escapeHtml(address)}" target="_blank" rel="noopener noreferrer" data-no-swup>${image}${escapeHtml(approved.displayText)}</a>`);
  }
  return links.length ? `<div class="flex flex-wrap items-center justify-center gap-3">${links.join('\n')}</div>\n` : '<!-- No approved filing is configured. -->\n';
}

export function configure() {
  const shared = JSON.parse(readFileSync(new URL('site.json', releaseRoot), 'utf8'));
  if (shared.schemaVersion !== 1 || !shared.site) throw new Error('Unsupported public site configuration');
  const site = shared.site;
  const origin = publicHttps(site.url, 'site.url');
  if (origin.pathname !== '/' || origin.search || origin.hash) throw new Error('site.url must contain only the origin');
  if (site.blogBase !== '/blog/') throw new Error('This release assembles the blog at /blog/');
  for (const key of ['title', 'author', 'description', 'language']) {
    if (typeof site[key] !== 'string' || !site[key].trim()) throw new Error(`Missing site.${key}`);
  }
  const siteFile = new URL('site.yaml', contentConfig);
  const siteConfig = JSON.parse(readFileSync(siteFile, 'utf8'));
  Object.assign(siteConfig, { site: origin.origin, base: site.blogBase, title: site.title, subtitle: site.description, lang: site.language.replace('-', '_') });
  siteConfig.banner ??= {};
  siteConfig.banner.homeText = { ...siteConfig.banner.homeText, title: site.title, subtitle: [site.description], typewriter: { enable: false, speed: 100, loop: false } };
  const profileFile = new URL('profile.yaml', contentConfig);
  const profile = JSON.parse(readFileSync(profileFile, 'utf8'));
  profile.name = site.author;
  const filingHtml = renderFilingLinks(shared.filing);
  // YAML accepts JSON. Retaining JSON here makes this preparatory step dependency-free.
  writeFileSync(siteFile, `${JSON.stringify(siteConfig, null, 2)}\n`);
  writeFileSync(profileFile, `${JSON.stringify(profile, null, 2)}\n`);
  writeFileSync(new URL('footer.html', contentConfig), filingHtml);
  console.log('Public blog configuration generated; unapproved filing entries are hidden.');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) configure();
