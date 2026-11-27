// Build-time validation shared by the blog and ship. It does not verify approval.
const officialHosts = {
  icp: new Set(['beian.miit.gov.cn']),
  publicSecurity: new Set(['beian.mps.gov.cn', 'www.beian.gov.cn', 'beian.gov.cn']),
};

export function validateFilingRecord(kind, record) {
  if (!Object.hasOwn(officialHosts, kind)) throw Error(`Unknown filing kind: ${kind}`);
  if (record?.approved !== true) return null;
  if (typeof record.displayText !== 'string' || !record.displayText.trim()) {
    throw Error(`${kind}: approved requires the complete issued displayText`);
  }
  let address;
  try { address = new URL(record.url); } catch { throw Error(`${kind}: an official HTTPS query URL is required`); }
  if (address.protocol !== 'https:' || address.username || address.password || address.port || !officialHosts[kind].has(address.hostname)) {
    throw Error(`${kind}: use the official HTTPS query URL without credentials or a custom port`);
  }
  let iconPath = '';
  if (kind === 'publicSecurity') {
    iconPath = record.iconPath;
    if (typeof iconPath !== 'string' || !iconPath.startsWith('/blog/images/filing/') || !/^\/blog\/images\/filing\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp|svg)$/i.test(iconPath)) {
      throw Error('publicSecurity: place the official icon in content/public/images/filing/ and use its /blog/images/filing/ ASCII image path');
    }
  }
  return { displayText: record.displayText.trim(), url: address.href, iconPath };
}
