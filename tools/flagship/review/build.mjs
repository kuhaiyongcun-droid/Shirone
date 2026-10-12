import { build } from 'esbuild';
import { mkdir, readFile, writeFile, cp, rm } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(root, '../../..');
const destination = path.join(root, 'dist');
const catalogPath = path.join(root, '.catalog-runtime.mjs');
for (const name of ['flagship.glb', 'archive.glb', 'overview.webp', 'archive.webp']) {
  try { await readFile(path.join(root, 'public/assets', name)); }
  catch { throw Error(`Missing ${name}: restore review-assets.zip as described in README.md before building.`); }
}
await build({
  stdin: { contents: `import Key from './src/i18n/i18nKey.ts';
    import { i18n } from './src/i18n/translation.ts';
    import { siteConfig } from './src/config/siteConfig.ts';
    const result={};
    for(const lang of ['zh_CN','en']){siteConfig.lang=lang;result[lang]={};
      for(const key of Object.values(Key).filter(k=>k.startsWith('flagshipReview'))) result[lang][key]=i18n(key);
    } export default result;`, resolveDir: repo, loader: 'ts' },
  bundle: true, platform: 'node', format: 'esm', outfile: catalogPath,
});
const catalog = (await import(pathToFileURL(catalogPath))).default;
await rm(catalogPath);
await rm(destination, { recursive: true, force: true }); await mkdir(destination, { recursive: true });
await cp(path.join(root, 'public'), destination, { recursive: true });
const dracoSource = path.join(root, 'node_modules/three/examples/jsm/libs/draco/gltf');
await mkdir(path.join(destination, 'assets/draco'), { recursive: true });
for (const name of ['draco_wasm_wrapper.js', 'draco_decoder.wasm']) await cp(path.join(dracoSource, name), path.join(destination, 'assets/draco', name));
await cp(path.join(root, 'node_modules/three/LICENSE'), path.join(destination, 'assets/THREE-LICENSE.txt'));
const result = await build({ entryPoints: { app: path.join(root, 'src/app.mjs') },
  outdir: destination, bundle: true, splitting: true, format: 'esm', target: ['es2022'], minify: true,
  metafile: true, legalComments: 'linked', chunkNames: 'chunks/[name]-[hash]',
  plugins: [{ name: 'review-catalog', setup(build) {
    build.onResolve({ filter: /^virtual:review-catalog$/ }, () => ({ path: 'catalog', namespace: 'review' }));
    build.onLoad({ filter: /.*/, namespace: 'review' }, () => ({ contents: JSON.stringify(catalog), loader: 'json' }));
  } }]
});
let html = await readFile(path.join(root, 'src/index.html'), 'utf8');
html = html.replace(/\{\{(\w+)\}\}/g, (_, key) => {
  const value = catalog.zh_CN['flagshipReview' + key];
  if (!value) throw Error(`Untranslated ${key}`);
  return value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
});
await writeFile(path.join(destination, 'index.html'), html);
await writeFile(path.join(destination, 'build-manifest.json'), JSON.stringify({
  revision: 'review-study-01', three: '0.186.1', assets: result.metafile.outputs,
  browser_verified: false, source: 'tools/flagship/review', locales: ['zh_CN', 'en'],
}, null, 2) + '\n');
console.log(`Built ${destination}`);
