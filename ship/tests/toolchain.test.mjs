import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFile, realpath } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root=fileURLToPath(new URL('../',import.meta.url));
test('a new build rejects implicit historical source before resolving assets or creating output',()=>{
  for(const args of [[],['--snapshot=public-fixture/snapshot.json'],['--snapshot-sha256='+'a'.repeat(64)]]){
    const result=spawnSync(process.execPath,[path.join(root,'build.mjs'),...args],{cwd:root,encoding:'utf8',windowsHide:true});
    assert.notEqual(result.status,0);
    assert.match(result.stderr,/Explicit --snapshot and --snapshot-sha256 are required/);
  }
});
test('declared Three and esbuild versions resolve physically inside the independent project',async()=>{
  const packageConfig=JSON.parse(await readFile(path.join(root,'package.json'),'utf8'));
  const modules=await realpath(path.join(root,'node_modules'));
  for(const [name,version] of Object.entries({...packageConfig.dependencies,...packageConfig.devDependencies})){
    const installedRoot=await realpath(path.join(modules,name));
    const rel=path.relative(modules,installedRoot);
    assert.ok(rel!== '..'&&!rel.startsWith('..'+path.sep)&&!path.isAbsolute(rel));
    const installed=JSON.parse(await readFile(path.join(installedRoot,'package.json'),'utf8'));
    assert.equal(installed.name,name);assert.equal(installed.version,version);
  }
});
test('the copied local esbuild native dependency executes a tiny in-memory transform',()=>{
  const require=createRequire(new URL('../package.json',import.meta.url));
  const esbuild=require('./node_modules/esbuild');
  assert.equal(esbuild.version,'0.28.2');
  const transformed=esbuild.transformSync('const value: number = 2;',{loader:'ts',minify:true});
  assert.match(transformed.code,/const value=2/);
});
