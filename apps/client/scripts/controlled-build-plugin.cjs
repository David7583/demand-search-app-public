// Minimal build-only adapter for @tarojs/service 4.3.2.
// API contract reference: Taro CLI (MIT), https://github.com/NervJS/taro/tree/v4.3.2/packages/taro-cli/src/presets
const fs = require('node:fs')
const path = require('node:path')
module.exports = ctx => {
  const hookNames = ['modifyAppConfig', 'modifyWebpackChain', 'modifyViteConfig', 'modifyBuildAssets', 'modifyMiniConfigs', 'modifyComponentConfig', 'modifyRunnerOpts', 'onCompilerMake', 'onParseCreateElement', 'onBuildStart', 'onBuildFinish', 'onBuildComplete']
  for (const name of hookNames) ctx.registerMethod(name)
  ctx.registerMethod('writeFileToDist', ({ filePath, content }) => {
    const output = path.resolve(ctx.paths.outputPath)
    const target = path.resolve(output, filePath)
    if (!target.startsWith(output + path.sep)) throw new Error('Output file escapes build directory')
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, content)
  })
  ctx.registerMethod('generateProjectConfig', ({ srcConfigName, distConfigName }) => {
    const source = path.resolve(ctx.paths.appPath, srcConfigName)
    if (!source.startsWith(ctx.paths.appPath + path.sep)) throw new Error('Project config path escapes application')
    if (!fs.existsSync(source)) return
    const value = JSON.parse(fs.readFileSync(source, 'utf8'))
    ctx.writeFileToDist({ filePath: distConfigName, content: JSON.stringify({ ...value, miniprogramRoot: './' }, null, 2) })
  })
  ctx.registerMethod('generateFrameworkInfo', () => ctx.writeFileToDist({
    filePath: '.frameworkinfo',
    content: JSON.stringify({ toolName: 'Taro', toolCliVersion: 'demand-search-controlled-build/1', toolFrameworkVersion: '4.3.2' })
  }))
  ctx.registerCommand({ name: 'build', async fn({ config, options }) {
    const forward = (name, opts, initialVal) => ctx.applyPlugins({ name, opts, ...(initialVal === undefined ? {} : { initialVal }) })
    const callbacks = {
      modifyAppConfig: appConfig => forward('modifyAppConfig', { appConfig }),
      modifyViteConfig: (viteConfig, data, viteCompilerContext) => forward('modifyViteConfig', { viteConfig, data, viteCompilerContext }, viteConfig),
      modifyBuildAssets: (assets, miniPlugin) => forward('modifyBuildAssets', { assets, miniPlugin }, assets),
      modifyMiniConfigs: configMap => forward('modifyMiniConfigs', { configMap }),
      modifyComponentConfig: (componentConfig, config) => forward('modifyComponentConfig', { componentConfig, config }),
      onCompilerMake: (compilation, compiler, plugin) => forward('onCompilerMake', { compilation, compiler, plugin }),
      onParseCreateElement: (nodeName, componentConfig) => forward('onParseCreateElement', { nodeName, componentConfig }),
      onBuildFinish: opts => forward('onBuildFinish', opts),
    }
    await ctx.applyPlugins('onBuildStart')
    await ctx.applyPlugins({ name: options.platform, opts: { config: { ...config, ...callbacks, isWatch: options.isWatch, mode: options.isWatch ? 'development' : 'production' } } })
    await ctx.applyPlugins('onBuildComplete')
  } })
}
