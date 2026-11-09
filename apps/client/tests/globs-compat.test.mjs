import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import Module, { createRequire } from 'node:module';

// npm test runs with apps/client as cwd. No .local, upstream test install or
// developer machine path is required.
const appRoot = process.cwd();
const appRequire = createRequire(path.join(appRoot, 'package.json'));
assert.equal(appRequire('./package.json').name, 'demand-search-client');
const scssEntry = appRequire.resolve('scss-bundle');
const scssRequire = createRequire(scssEntry);
const globsEntry = scssRequire.resolve('globs');
const current = scssRequire('globs');
const globRequire = createRequire(globsEntry);
const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'dsa-globs-regression-'));
const toPosix = p => p.replaceAll('\\', '/');
const write = (name, text) => {
  const file = path.join(fixture, name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
};
after(() => {
  // Delete only the uniquely created synthetic tree; never a computed ancestor.
  const resolved = path.resolve(fixture);
  assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()));
  assert.match(path.basename(resolved), /^dsa-globs-regression-/);
  fs.rmSync(resolved, { recursive: true, force: true });
});
for (const f of ['a.scss', 'B.scss', 'c.css', '.hidden.scss', 'sub/nested.scss', 'sub/.dot.scss', 'space name/a.scss', 'unicode-椅子.scss']) write(f, '.x {color:red;}');
write('bundle/_tokens.scss', '$color: red;\n.marker { color: $color; }\n');
write('bundle/sub.scss', '@import "tokens";\n.sub { color: $color; }\n');
write('bundle/entry.scss', '@import "tokens";\n@import "sub";\n.main { color: $color; }\n');
write('bundle/include-entry.scss', '@import "outside";\n.main { width: $size; }\n');
write('include/_outside.scss', '$size: 12px;\n');
write('node_modules/pkg/_tone.scss', '$tone: blue;\n');
write('bundle/tilde-entry.scss', '@import "~pkg/tone";\n.main { color: $tone; }\n');

const asyncCall = (patterns, options) => new Promise((resolve, reject) =>
  current(patterns, options, (error, files) => error ? reject(error) : resolve(files)));
const sorted = files => [...files].sort((a, b) => a.localeCompare(b, 'en'));
const top = ['a.scss', 'B.scss', 'unicode-椅子.scss'];
const bundle = ['bundle/_tokens.scss', 'bundle/entry.scss', 'bundle/include-entry.scss', 'bundle/sub.scss', 'bundle/tilde-entry.scss'];
const all = sorted([...top, ...bundle, 'include/_outside.scss', 'node_modules/pkg/_tone.scss', 'space name/a.scss', 'sub/nested.scss']);
const cases = [
  ['single string', '*.scss', {}, top],
  ['array retains duplicates', ['*.scss', 'a.scss'], {}, [...top, 'a.scss']],
  ['empty array', [], {}, []],
  ['no match', 'missing/*.scss', {}, []],
  ['brace', '{a,B}.scss', {}, ['a.scss', 'B.scss']],
  ['globstar', '**/*.scss', {}, all],
  ['dot', '**/*.scss', { dot: true }, sorted([...all, '.hidden.scss', 'sub/.dot.scss'])],
  ['ignore', '**/*.scss', { ignore: ['bundle/**', 'node_modules/**'] }, all.filter(f => !f.startsWith('bundle/') && !f.startsWith('node_modules/'))],
  ['directories with mark', '*', { mark: true }, sorted([...top, 'c.css', 'bundle/', 'include/', 'node_modules/', 'space name/', 'sub/'])],
  ['nodir', '*', { nodir: true }, sorted([...top, 'c.css'])],
  ['absolute option', '*.scss', { absolute: true }, top.map(f => toPosix(path.join(fixture, f)))],
  ['absolute pattern', toPosix(fixture) + '/*.scss', {}, top.map(f => toPosix(path.join(fixture, f)))],
  ['dot relative', './*.scss', {}, top.map(f => './' + f)],
  ['matchBase', 'nested.scss', { matchBase: true }, ['sub/nested.scss']],
  ['noglobstar', '**/*.scss', { noglobstar: true }, sorted([...bundle, 'include/_outside.scss', 'space name/a.scss', 'sub/nested.scss'])],
  ['nobrace', '{a,B}.scss', { nobrace: true }, []],
  ['noext', '+(a|B).scss', { noext: true }, []],
  ['extglob', '+(a|B).scss', {}, ['a.scss', 'B.scss']],
  ['nocase', 'b.SC*S', { nocase: true }, ['B.scss']],
// Windows runners may expose an 8.3 TEMP alias; realpath must return the canonical path.
  ['realpath', '*.scss', { realpath: true }, top.map(f => fs.realpathSync.native(path.join(fixture, f)))],
  ['spaces', 'space name/*.scss', {}, ['space name/a.scss']],
  ['unicode', 'unicode-*.scss', {}, ['unicode-椅子.scss']],
  ['platform separator', process.platform === 'win32' ? 'sub\\*.scss' : 'sub/*.scss', {}, ['sub/nested.scss']],
];
for (const [name, patterns, options, expected] of cases) test('globs contract: ' + name, async () => {
  assert.deepEqual(current.sync(patterns, { cwd: fixture, ...options }), expected);
  // Concurrent patterns retain duplicates, but their completion order is not fixed.
  assert.deepEqual(sorted(await asyncCall(patterns, { cwd: fixture, ...options })), sorted(expected));
});

test('globs callback shorthand defers the empty result', async () => {
  let synchronous = true;
  const result = new Promise((resolve, reject) => current([], (error, files) => {
    try { assert.equal(synchronous, false); assert.equal(error, null); assert.deepEqual(files, []); resolve(); }
    catch (caught) { reject(caught); }
  }));
  synchronous = false;
  await result;
});
test('globs leaves caller options unchanged', () => {
  const options = { cwd: fixture, nodir: true };
  current.sync('*.scss', options);
  assert.deepEqual(options, { cwd: fixture, nodir: true });
});
test('globs sync keeps pattern order and duplicate paths', () =>
  assert.deepEqual(current.sync(['B.scss', 'a.scss', 'B.scss'], { cwd: fixture }), ['B.scss', 'a.scss', 'B.scss']));
test('globs nosort retains the complete matching file set', () =>
  assert.deepEqual(sorted(current.sync('*.scss', { cwd: fixture, nosort: true })), top));
test('globs rejects unsupported legacy options explicitly', async () => {
  assert.throws(() => current.sync('*.scss', { nonull: true }), { code: 'GLOBS_UNSUPPORTED_OPTION' });
  await assert.rejects(asyncCall('*.scss', { nonull: true }), { code: 'GLOBS_UNSUPPORTED_OPTION' });
});
test('globs rejects oversized and malformed input before traversal', async () => {
  for (const [patterns, code] of [[new Array(257).fill('*'), 'GLOBS_PATTERN_LIMIT'], ['x'.repeat(4097), 'GLOBS_PATTERN_LIMIT'], [[null], 'GLOBS_PATTERN_TYPE']]) {
    assert.throws(() => current.sync(patterns), { code });
    await assert.rejects(asyncCall(patterns, {}), { code });
  }
  assert.throws(() => current('*', {}), { code: 'GLOBS_CALLBACK_TYPE' });
  assert.throws(() => current.sync('*', 'wrong'), { code: 'GLOBS_OPTIONS_TYPE' });
});
test('globs preserves async completion order and invokes an error callback once', async () => {
  const original = Module._load;
  let fake = pattern => new Promise(resolve => setTimeout(() => resolve([pattern]), pattern === 'slow' ? 15 : 1));
  let injected;
  Module._load = function (request, parent) {
    if (request === 'glob/raw' && parent.filename === globsEntry) return { glob: (...args) => fake(...args), globSync: () => [] };
    return original.apply(this, arguments);
  };
  delete appRequire.cache[globsEntry];
  try { injected = scssRequire('globs'); }
  finally { Module._load = original; delete appRequire.cache[globsEntry]; }
  const call = patterns => new Promise((resolve, reject) => injected(patterns, (error, files) => error ? reject(error) : resolve(files)));
  assert.deepEqual(await call(['slow', 'fast']), ['fast', 'slow']);
  const expectedError = new Error('synthetic read failure');
  fake = () => Promise.reject(expectedError);
  let count = 0;
  await new Promise((resolve, reject) => injected(['a', 'b'], (error, files) => {
    try { count++; assert.equal(error, expectedError); assert.deepEqual(files, []); setTimeout(resolve, 20); }
    catch (caught) { reject(caught); }
  }));
  assert.equal(count, 1);
});

test('real SCSS bundle and Sass compile preserve partials, dedupe, includes and tilde imports', async () => {
  const { Bundler } = appRequire('scss-bundle');
  const sass = appRequire('sass');
  const expected = [
    ['bundle/entry.scss', [], [], '.marker{color:red}.marker{color:red}.sub{color:red}.main{color:red}', 2],
    ['bundle/entry.scss', [toPosix(fixture) + '/bundle/_*.scss'], [], '.marker{color:red}.sub{color:red}.main{color:red}', 1],
    ['bundle/include-entry.scss', [], [path.join(fixture, 'include')], '.main{width:12px}', 0],
    ['bundle/tilde-entry.scss', [], [], '.main{color:blue}', 0],
  ];
  for (const [entry, dedupe, includes, css, markerCount] of expected) {
    const result = await new Bundler({}, fixture).bundle(entry, dedupe, includes);
    assert.equal(result.found, true);
    assert.doesNotMatch(result.bundledContent, /@import/);
    assert.equal(sass.compileString(result.bundledContent).css, sass.compileString(css).css);
    assert.equal((result.bundledContent.match(/\.marker/g) || []).length, markerCount);
  }
});
test('real SCSS bundle rejects excessive dedupe without a secondary callback crash', async () => {
  const { Bundler } = appRequire('scss-bundle');
  const result = await new Bundler({}, fixture).bundle('bundle/entry.scss', ['x'.repeat(4097)]);
  assert.equal(result.found, false);
});
test('globs uses actual maintained packages and the unbundled engine export', () => {
  assert.equal(scssRequire('globs/package.json').version, '0.1.4-dsa.1');
  assert.match(globRequire.resolve('glob/raw'), /[\\/]index\.js$/);
  assert.equal(globRequire('glob/package.json').version, '14.0.3');
  const engineRequire = createRequire(globRequire.resolve('glob/raw'));
  assert.equal(engineRequire('minimatch/package.json').version, '11.0.4');
});
for (const kind of ['globparts', 'brace', 'extglob', 'limit', 'abort']) test('bounded globs security regression: ' + kind, () => {
  const result = spawnSync(process.execPath, ['--max-old-space-size=96', path.join(testDirectory, 'helpers/globs-security.mjs'), kind, fixture], {
    encoding: 'utf8', timeout: 5000, windowsHide: true, cwd: appRoot,
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout.trim());
  assert.equal(output.ok, true);
  assert.ok(output.elapsed_ms < 4500, JSON.stringify(output));
});
