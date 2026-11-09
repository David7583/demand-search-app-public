import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import http from 'node:http'
import { createRequire } from 'node:module'
import { pathToFileURL, fileURLToPath } from 'node:url'

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const analysis = path.resolve(clientRoot, '../../.local/build-security')
await fs.mkdir(analysis, { recursive: true })
const requireD = createRequire(path.join(clientRoot, 'package.json'))
const runnerRoot = path.dirname(requireD.resolve('@tarojs/vite-runner/package.json'))
const viteRoot = path.dirname(requireD.resolve('vite/package.json'))
const vite = await import(pathToFileURL(path.join(viteRoot, 'dist/node/index.js')).href)
const { viteStaticCopy } = await import(pathToFileURL(requireD.resolve('vite-plugin-static-copy')).href)
assert.equal(requireD('@tarojs/vite-runner/package.json').version, '4.3.2-dsa.1')
assert.equal(requireD('vite/package.json').version, '6.4.5')
const runRoot = await fs.mkdtemp(path.join(analysis, 'real-regression-'))
const observations = { synthetic_inputs_only: true, clientRoot, runRoot, tests: [] }
process.env.NODE_ENV = 'development'

function runner(relative) { return requireD(path.join(runnerRoot, 'dist', relative)) }
function clone(value) { return structuredClone(value) }

async function configs(base, importer) {
  const h5 = clone(runner('defaultConfig/defaultConfig.h5.js').default)
  Object.assign(h5, {
    mode: 'development', framework: 'react', sourceRoot: 'web', outputRoot: 'out',
    publicPath: '/', designWidth: 750, deviceRatio: {}, entry: { app: path.join(base, 'web/main.js') },
    devServer: { host: '127.0.0.1', open: false, fs: { strict: true, allow: [path.join(base, 'web')] } },
    sassLoaderOption: { importer },
  })
  h5.postcss.pxtransform.enable = false
  h5.postcss.htmltransform.enable = false
  const context = { cwd: base, sourceDir: path.join(base, 'web'), app: { configPath: path.join(base, 'web/app.config.ts') }, taroConfig: h5 }
  const h5Plugin = runner('h5/config.js').default(context)
  const h5Config = await h5Plugin.config()
  return { h5Config }
}

test('actual desktop H5 legacy Sass options compile through Vite with asynchronous callback importers', async () => {
  assert.ok(requireD.resolve('sass'))
  let calls = 0
  const importer = (url, _previous, done) => {
    calls++
    setTimeout(() => done(url === 'synthetic-virtual' ? { contents: '$brand: #123456;' } : null), 2)
  }
  const { h5Config } = await configs(runRoot, importer)
  const results = []
  for (const [name, config] of [['h5', h5Config]]) {
    assert.equal(config.css.preprocessorOptions.scss.api, 'legacy')
    const resolved = await vite.resolveConfig({
      configFile: false, root: clientRoot, cacheDir: path.join(runRoot, 'sass-cache-' + name),
      logLevel: 'silent', css: { preprocessorOptions: config.css.preprocessorOptions },
    }, 'build')
    const result = await vite.preprocessCSS('@import "synthetic-virtual"; .card { color: $brand; }', path.join(runRoot, name + '.scss'), resolved)
    assert.match(result.code, /color:\s*#123456/)
    results.push({ target: name, css: result.code })
  }
  assert.equal(calls, 1)
  observations.tests.push({ test: 'sass', importer_calls: calls, results })
})

function request(port, target, headers = {}, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, path: target, method, headers }, res => {
      const parts = []
      res.on('data', chunk => parts.push(chunk))
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(parts).toString('utf8') }))
    })
    req.setTimeout(4000, () => req.destroy(new Error('fixture request timed out')))
    req.on('error', reject)
    req.end()
  })
}

test('real static-copy handles Windows normalized paths and renames while dev denies traversal, adjacent files and foreign CORS', { timeout: 45000 }, async () => {
  const web = path.join(runRoot, 'web')
  const copySource = path.join(runRoot, 'copy-source')
  await fs.mkdir(web, { recursive: true })
  await fs.mkdir(copySource, { recursive: true })
  await fs.writeFile(path.join(web, 'index.html'), '<!doctype html><title>synthetic fixture</title>')
  await fs.writeFile(path.join(copySource, 'visible.txt'), 'SYNTHETIC_ALLOWED_COPY')
  const privateFile = path.join(runRoot, 'neighbor.txt')
  await fs.writeFile(privateFile, 'SYNTHETIC_NEIGHBOR_MUST_NOT_BE_SERVED')
  await fs.writeFile(path.join(web, '.env.synthetic'), 'SYNTHETIC_ENV_MUST_NOT_BE_SERVED')
  const { convertCopyOptions } = runner('utils/index.js')
  const patterns = [
    { from: vite.normalizePath(copySource), to: 'out/copied' },
    { from: vite.normalizePath(path.join(copySource, 'visible.txt')), to: 'out/renamed/approved.txt' },
  ]
  const targets = convertCopyOptions({ outputRoot: 'out', copy: { patterns } })
  assert.ok(targets.every(item => !item.src.includes('\\')))
  const { h5Config } = await configs(runRoot)
  assert.equal(h5Config.server.cors, false, 'Use actual maintained Taro default, not a test replacement')
  let server
  try {
    server = await vite.createServer({
      configFile: false, root: web, publicDir: false, appType: 'mpa',
      cacheDir: path.join(runRoot, 'copy-cache'), logLevel: 'silent',
      plugins: [viteStaticCopy({ targets })],
      server: { ...h5Config.server, host: '127.0.0.1', port: 19086, strictPort: true, open: false, hmr: false },
    })
    await server.listen()
    const port = server.httpServer.address().port
    assert.notEqual(port, 8000)
    for (const target of ['/copied/visible.txt', '/renamed/approved.txt']) {
      const response = await request(port, target)
      assert.equal(response.status, 200, target)
      assert.equal(response.body, 'SYNTHETIC_ALLOWED_COPY', target)
    }
    const denied = ['/copied/../neighbor.txt', '/copied/%2e%2e/neighbor.txt', '/copied/%252e%252e/neighbor.txt',
      '/copied/..%5cneighbor.txt', '/copied/%2e%2e%5cneighbor.txt', '/neighbor.txt', '/.env.synthetic',
      '/@fs/' + vite.normalizePath(privateFile)]
    const results = []
    for (const target of denied) {
      const response = await request(port, target)
      assert.ok([400,403,404].includes(response.status), target + ': ' + response.status)
      assert.ok(!response.body.includes('SYNTHETIC_NEIGHBOR_MUST_NOT_BE_SERVED'), target)
      assert.ok(!response.body.includes('SYNTHETIC_ENV_MUST_NOT_BE_SERVED'), target)
      results.push({ target, status: response.status })
    }
    const foreign = await request(port, '/copied/visible.txt', { Origin: 'https://untrusted.invalid' })
    assert.equal(foreign.headers['access-control-allow-origin'], undefined)
    const preflight = await request(port, '/copied/visible.txt', { Origin: 'https://untrusted.invalid', 'Access-Control-Request-Method': 'GET' }, 'OPTIONS')
    assert.equal(preflight.headers['access-control-allow-origin'], undefined)
    const host = await request(port, '/', { Host: 'untrusted.invalid' })
    assert.equal(host.status, 403)
    observations.tests.push({ test: 'static-copy-dev', port, windows_native_paths: process.platform === 'win32', traversal_and_adjacent_denied: results, foreign_cors_allowed: false, invalid_host_status: host.status })
  } finally { if (server) await server.close() }
  const buildDir = path.join(runRoot, 'copy-build')
  assert.ok(path.resolve(buildDir).startsWith(path.resolve(runRoot) + path.sep))
  await vite.build({ configFile: false, root: web, publicDir: false, logLevel: 'silent',
    cacheDir: path.join(runRoot, 'copy-build-cache'), plugins: [viteStaticCopy({ targets })],
    build: { outDir: buildDir, emptyOutDir: false, minify: false } })
  assert.equal(await fs.readFile(path.join(buildDir, 'copied/visible.txt'), 'utf8'), 'SYNTHETIC_ALLOWED_COPY')
  assert.equal(await fs.readFile(path.join(buildDir, 'renamed/approved.txt'), 'utf8'), 'SYNTHETIC_ALLOWED_COPY')
  observations.tests.push({ test: 'static-copy-build', directory_and_rename_preserved: true })
})

test.after(async () => {
  await fs.writeFile(path.join(runRoot, 'observations.json'), JSON.stringify(observations, null, 2))
  console.log('Synthetic regression evidence: ' + runRoot)
})
