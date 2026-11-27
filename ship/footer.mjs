import { validateFilingRecord } from '../scripts/filing.mjs';

export const escapeHtml = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
function approvedLink(kind, record) {
  const approved = validateFilingRecord(kind, record);
  if (!approved) return '';
  const icon = kind === 'publicSecurity' ? `<img src="${escapeHtml(approved.iconPath)}" width="20" height="20" alt="">` : '';
  return `<a href="${escapeHtml(approved.url)}" target="_blank" rel="noopener noreferrer">${icon}${escapeHtml(approved.displayText)}</a>`;
}
export function renderFooter(config, labels) {
  if (config?.schemaVersion !== 1 || !config.site?.author || config.site.blogBase !== '/blog/') throw Error('Unsupported site configuration');
  return [`<span>© ${escapeHtml(config.site.author)}</span>`, `<a href="/blog/about/">${escapeHtml(labels.about)}</a>`, approvedLink('icp', config.filing?.icp), approvedLink('publicSecurity', config.filing?.publicSecurity)].filter(Boolean).join('\n');
}
