import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, copyFile, stat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { inspectContractFiles } from './verify-assets.mjs';
import { escapeHtml, renderFooter } from './footer.mjs';
import { readSourceSelection, SUPPORT_FILES } from './source-selection.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const args={};
for(const arg of process.argv.slice(2)){const match=/^--(out|snapshot|snapshot-sha256)=(.+)$/.exec(arg);if(!match||args[match[1]])throw Error('Unknown/duplicate build argument');args[match[1]]=match[2];}
if(!args.snapshot||!args['snapshot-sha256'])throw Error('Explicit --snapshot and --snapshot-sha256 are required; no historical source fallback is used for a new build');
// Resolve only exact declared dependencies physically inside this project.
const require=createRequire(import.meta.url);
const packageConfig=JSON.parse(await readFile(path.join(root,'package.json'),'utf8'));
for(const [name,version] of Object.entries({...packageConfig.dependencies,...packageConfig.devDependencies})){
  const packageRoot=path.join(root,'node_modules',name);
  let actualRoot,installed;
  try{actualRoot=await realpath(packageRoot);installed=JSON.parse(await readFile(path.join(actualRoot,'package.json'),'utf8'));}
  catch(error){throw Error(`Missing local ${name}@${version}. Restore this project's known dependency package or explicitly install its frozen lockfile; build never installs dependencies.`,{cause:error});}
  const relative=path.relative(await realpath(path.join(root,'node_modules')),actualRoot);
  if(relative.startsWith('..'+path.sep)||relative==='..'||path.isAbsolute(relative))throw Error(`${name} resolves outside ship/node_modules`);
  if(installed.name!==name||installed.version!==version)throw Error(`Expected ${name}@${version}; found ${installed.name}@${installed.version}`);
}
const { build }=require('./node_modules/esbuild');
if(process.env.ESBUILD_BINARY_PATH)throw Error('External ESBUILD_BINARY_PATH overrides are not supported by this independent build');
const esbuildRoot=await realpath(path.join(root,'node_modules/esbuild'));
const platformPackage=`@esbuild/${process.platform}-${process.arch}`;
const nativeRequire=createRequire(path.join(esbuildRoot,'package.json'));
let nativePackageFile;
try{nativePackageFile=await realpath(nativeRequire.resolve(platformPackage+'/package.json'));}
catch(error){throw Error(`Missing local ${platformPackage}@${packageConfig.devDependencies.esbuild}. Restore/install the matching platform dependency explicitly; no download is attempted.`,{cause:error});}
const nativeRelative=path.relative(await realpath(path.join(root,'node_modules')),nativePackageFile);
if(nativeRelative==='..'||nativeRelative.startsWith('..'+path.sep)||path.isAbsolute(nativeRelative))throw Error('esbuild platform package resolves outside ship/node_modules');
if(JSON.parse(await readFile(nativePackageFile,'utf8')).version!==packageConfig.devDependencies.esbuild)throw Error('esbuild platform package version mismatch');
const toolchain={node:process.version,esbuild:packageConfig.devDependencies.esbuild,three:packageConfig.dependencies.three};
console.log(JSON.stringify({toolchain,dependencyScope:'ship/node_modules'}));
const name=args.out||'dist';
if(!/^dist(?:-[a-zA-Z0-9_-]+)?$/.test(name))throw Error('Output must be a new dist[-NAME] child');
const out=path.join(root,name);
try{await stat(out);throw Error('Refusing to overwrite an existing build');}catch(e){if(e.code!=='ENOENT')throw e;}
const manifestPath=path.join(root,'build-manifest-'+name+'.json');
try{await stat(manifestPath);throw Error('Refusing to overwrite an existing build manifest');}catch(e){if(e.code!=='ENOENT')throw e;}
const config=JSON.parse(await readFile(path.join(root,'../site.json'),'utf8'));
const canonical=new URL(config.site.url);if(canonical.protocol!=='https:'||canonical.username||canonical.password)throw Error('Public site URL must be HTTPS');
const selected=await readSourceSelection({snapshot:args.snapshot,snapshotSha256:args['snapshot-sha256']});
const runtime=await inspectContractFiles(selected.publicRoot,{expectedSource:selected.source,expectedContract:selected.contract,requireViewerCompatibility:true});
if(!runtime.ready)throw Error('Complete source package required');
const translation=await build({stdin:{contents:`import Key from './i18n/i18nKey.ts';import {i18n} from './i18n/translation.ts';import {siteConfig} from './config/siteConfig.ts';
const result={},marks={},keys=Object.values(Key).filter(k=>k.startsWith('flagshipReview')||k.startsWith('flagshipShip'));
for(const lang of ['en','zh_CN','zh_TW','es','id','ja','ko','th','tr','vi']){siteConfig.lang=lang;const row={};for(const key of keys){const value=i18n(key);if(!value?.trim())throw Error('Missing '+lang+'/'+key);const m=JSON.stringify((value.match(/\\{\\w+\\}/g)||[]).sort());if(lang==='en')marks[key]=m;else if(m!==marks[key])throw Error('Placeholder mismatch '+lang+'/'+key);row[key]=value;}if(['zh_CN','en'].includes(lang))result[lang]=row;}export default result;`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false});
const catalog=(await import('data:text/javascript;base64,'+Buffer.from(translation.outputFiles[0].contents).toString('base64'))).default;
const findPoster=scope=>runtime.references.frames.find(r=>r.scope===scope&&r.view_id===runtime.cameras.defaults[scope]&&r.light==='space').asset.uri;
const publicSite={author:config.site.author,sourceStage:selected.source.stage,assetPin:{source:selected.source,contract:selected.contract},posters:{ship:findPoster('exterior'),archive:findPoster('archive')}};
const result=await build({entryPoints:{app:path.join(root,'src/app.mjs')},outdir:out,bundle:true,write:false,splitting:true,format:'esm',target:['es2022'],minify:true,metafile:true,legalComments:'linked',chunkNames:'chunks/[name]-[hash]',nodePaths:[],plugins:[{name:'ship-public-data',setup(b){b.onResolve({filter:/^virtual:(review-catalog|ship-config)$/},args=>({path:args.path,namespace:'ship'}));b.onLoad({filter:/.*/,namespace:'ship'},args=>({contents:JSON.stringify(args.path==='virtual:review-catalog'?catalog:publicSite),loader:'json'}));}}]});
const labels=catalog.zh_CN;
const values={SITE_TITLE:config.site.title,AUTHOR:config.site.author,SITE_DESCRIPTION:config.site.description,SITE_URL:canonical.href,POSTER_URL:publicSite.posters.ship};
let html=await readFile(path.join(root,'src/index.html'),'utf8');
html=html.replace(/\{\{(\w+)\}\}/g,(_,key)=>{if(key==='FOOTER_HTML')return renderFooter(config,{about:labels.flagshipShipAbout});const value=values[key]??labels[key.startsWith('Ship')?'flagship'+key:'flagshipReview'+key];if(typeof value!=='string')throw Error('Missing HTML string '+key);return escapeHtml(value);});
await mkdir(out);
for(const f of result.outputFiles){await mkdir(path.dirname(f.path),{recursive:true});await writeFile(f.path,f.contents);}
const copied=[...runtime.files,...SUPPORT_FILES];
for(const relative of copied){await mkdir(path.dirname(path.join(out,relative)),{recursive:true});await copyFile(path.join(selected.publicRoot,relative),path.join(out,relative));}
await writeFile(path.join(out,'index.html'),html);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifest={schema:'ship-release-build-v1',createdAt:new Date().toISOString(),toolchain,sourceStage:selected.source.stage,sourceSceneSha256:runtime.contract.source_scene.sha256,contractRevision:runtime.contract.revision,contractPin:selected.contract,snapshot:selected.snapshot,snapshotSha256:selected.snapshotSha256||null,viewerCompatibility:runtime.compatibility,siteConfigSha256:sha(await readFile(path.join(root,'../site.json'))),defaultMode:'static',threeStarts:'explicit-enable-button',output:name,assets:[],browserVerified:false,lightingCalibrated:false};
for(const relative of ['index.html',...result.outputFiles.map(f=>path.relative(out,f.path).split(path.sep).join('/')),...copied]){const bytes=await readFile(path.join(out,relative));manifest.assets.push({path:relative,bytes:bytes.length,sha256:sha(bytes)});}
await writeFile(manifestPath,JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({output:out,files:manifest.assets.length,bytes:manifest.assets.reduce((n,r)=>n+r.bytes,0),sourceStage:selected.source.stage,browserVerified:false}));
