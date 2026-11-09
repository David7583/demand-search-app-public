import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const packageRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const source = fs.readFileSync(path.join(packageRoot, 'dist/mini/emit.js'), 'utf8')

function fixture({ minify = true, failAt = 0 } = {}) {
  const emitted = []
  const compressed = []
  const sequence = []
  const componentConfig = { thirdPartyComponents: new Set(['custom-wrapper']) }
  const template = {
    isSupportRecursive: false,
    isUseXS: true,
    buildTemplate() { sequence.push('base-before-pages'); return '<view>  base  </view>' },
    buildPageTemplate(_base, { path: name }) { sequence.push(name); return '<view>  page  </view>' },
    buildBaseComponentTemplate() { return '<view>  component  </view>' },
    buildCustomComponentTemplate() { return '<view>  wrapper  </view>' },
    buildXScript() { return 'var x = 1;' },
  }
  const requires = {
    'node:path': path,
    '@tarojs/helper': { promoteRelativePath: value => value },
    '@tarojs/shared': { isFunction: value => typeof value === 'function', isString: value => typeof value === 'string' },
    '../utils': { getComponentName: (_context, value) => value, prettyPrintJson: JSON.stringify },
    '../utils/component': { componentConfig },
    '../utils/constants': { baseTemplateName: 'base', baseCompName: 'comp', customWrapperName: 'custom-wrapper' },
    'html-minifier-terser': { async minify(value, options) {
      compressed.push({ value, options })
      await new Promise(resolve => setTimeout(resolve, 2))
      if (compressed.length === failAt) throw new Error('synthetic minifier failure')
      return value.replace(/  /g, ' ')
    } },
  }
  const exports = {}
  vm.runInNewContext(source, { exports, process: { env: { TARO_ENV: 'weapp' } }, require(name) {
    assert.ok(Object.hasOwn(requires, name), 'Unexpected dependency: ' + name)
    return requires[name]
  } }, { filename: 'maintained-mini-emit.js' })
  const context = {
    app: { name: 'app', config: {} },
    sourceDir: '/synthetic/src',
    taroConfig: { template, minifyXML: { collapseWhitespace: minify }, taroComponentsPath: '/synthetic/components' },
    pages: ['a', 'b'].map(name => ({ name, scriptPath: '/synthetic/src/' + name, config: {}, isNative: false })),
    nativeComponents: new Map(),
    fileType: { templ: '.wxml', xs: '.wxs' },
    getConfigPath: name => name + '.json',
    getTemplatePath: name => name + '.wxml',
    getTargetFilePath: (name, ext) => name + ext,
    getScriptPath: name => name + '.js',
  }
  const hookContext = { async resolve() { return null }, emitFile(asset) { emitted.push(asset) } }
  return { hook: exports.default(context)[0], hookContext, emitted, compressed, sequence }
}

test('awaits every page, base, component and custom-wrapper template before bundle completion', async () => {
  const state = fixture()
  await state.hook.generateBundle.call(state.hookContext, {}, {})
  const templates = state.emitted.filter(asset => asset.fileName.endsWith('.wxml'))
  assert.equal(templates.length, 5)
  assert.equal(state.compressed.length, 5)
  assert.deepEqual(state.sequence, ['base-before-pages', 'a', 'b'])
  assert.ok(state.emitted.every(asset => typeof asset.source === 'string'))
  assert.ok(templates.every(asset => !asset.source.includes('  ')))
  assert.ok(state.compressed.every(item => item.options.keepClosingSlash === true))
})

test('minifier rejection rejects the bundle and prevents subsequent template work', async () => {
  const state = fixture({ failAt: 2 })
  await assert.rejects(state.hook.generateBundle.call(state.hookContext, {}, {}), /synthetic minifier failure/)
  assert.equal(state.compressed.length, 2)
  assert.equal(state.emitted.filter(asset => asset.fileName.endsWith('.wxml')).length, 1)
})

test('disabled XML minification preserves the original template bytes', async () => {
  const state = fixture({ minify: false })
  await state.hook.generateBundle.call(state.hookContext, {}, {})
  const templates = state.emitted.filter(asset => asset.fileName.endsWith('.wxml'))
  assert.equal(state.compressed.length, 0)
  assert.equal(templates.length, 5)
  assert.ok(templates.every(asset => typeof asset.source === 'string' && asset.source.includes('  ')))
})
