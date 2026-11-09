import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const appRequire=createRequire(path.join(process.cwd(),'package.json'));
const scssRequire=createRequire(appRequire.resolve('scss-bundle'));
const globs=scssRequire('globs');
const globsRequire=createRequire(scssRequire.resolve('globs'));
const engineRequire=createRequire(globsRequire.resolve('glob/raw'));
const {Minimatch}=engineRequire('minimatch');
const kind=process.argv[2], cwd=process.argv[3], start=performance.now();
(async()=>{
 let detail={};
 if(kind==='globparts') {
  // Advisory GHSA-g3hv-75wg-m249: optimizer amplification with **/../.
  const pattern='**/../a/b/'.repeat(8)+'does-not-exist';
  const matcher=new Minimatch(pattern,{optimizationLevel:2,braceExpandMax:10000});
  assert.ok(matcher.set.length<=10000);
  // Pure optimizer input: no parent-directory filesystem traversal.
  detail.parts=matcher.set.length;
 } else if(kind==='brace') {
  // Brace product would exceed the new engine's documented 10k bound.
  const matcher=new Minimatch('{a,b}'.repeat(25)+'.scss',{braceExpandMax:10000});
  assert.ok(matcher.set.length<=10000);
  assert.deepEqual(globs.sync('{a,b}'.repeat(25)+'.scss',{cwd}),[]);
  detail.expanded=matcher.set.length;
 } else if(kind==='extglob') {
  const pattern='*('.repeat(180)+'a'+')'.repeat(180)+'z';
  assert.equal(new Minimatch(pattern).match('a'.repeat(300)+'y'),false);
  globs.sync(pattern,{cwd});
 } else if(kind==='limit') {
  assert.throws(()=>globs.sync('x'.repeat(4097),{cwd}),{code:'GLOBS_PATTERN_LIMIT'});
 } else if(kind==='abort') {
  const controller=new AbortController();
  let reads=0, afterReject=0, rejected=false;
  const instrumented={...fs,readdir(path,options,callback){
   reads++;if(rejected)afterReject++;
   controller.abort(new Error('synthetic-abort'));
   fs.readdir(path,options,callback);
  }};
  await assert.rejects(new Promise((resolve,reject)=>globs('**/*.scss',{cwd,signal:controller.signal,fs:instrumented},(error,files)=>{rejected=true;if(error) reject(error); else resolve(files);})),/synthetic-abort/);
  await new Promise(resolve=>setTimeout(resolve,50));
  assert.equal(afterReject,0);
  detail={reads,afterReject};
 }
 console.log(JSON.stringify({ok:true,kind,elapsed_ms:performance.now()-start,...detail}));
})().catch(e=>{console.error(e);process.exitCode=1;});
