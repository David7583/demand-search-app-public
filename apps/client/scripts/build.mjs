// Restricted local build entry. Uses the public @tarojs/service 4.3.2 API.
// Build hook names follow Taro's MIT-licensed CLI implementation:
// https://github.com/NervJS/taro/tree/v4.3.2/packages/taro-cli/src/presets
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Config, Kernel } from '@tarojs/service'

const appPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const platform = process.argv[2]
const isWatch = process.argv.includes('--watch')
if (!['h5', 'weapp'].includes(platform) || process.argv.slice(3).some(arg => arg !== '--watch')) throw new Error('Only h5/weapp and --watch are supported')
const workspace = path.resolve(appPath, '../..')
if (!appPath.startsWith(workspace + path.sep)) throw new Error('Build workspace boundary mismatch')
const mode = isWatch ? 'development' : 'production'
process.env.NODE_ENV = mode
process.env.TARO_ENV = platform
const config = new Config({ appPath, disableGlobalConfig: true })
await config.init({ command: 'build', mode })
const initial = config.initialConfig
if (!config.isInitSuccess || initial.framework !== 'react' || initial.compiler?.type !== 'vite' || initial.sourceRoot !== 'src') throw new Error('Unsupported project configuration')
if (initial.plugins?.length || initial.presets?.length) throw new Error('Only the pinned platform and framework plugins are enabled')
const output = path.resolve(appPath, initial.outputRoot)
const allowed = [path.join(appPath, 'dist', platform), path.join(workspace, '.local', 's2-client', platform), path.join(workspace, '.local', 's5-client', platform)]
if (!allowed.includes(output)) throw new Error('Output must be the project dist or isolated staging directory')
fs.mkdirSync(output, { recursive: true })
const kernel = new Kernel({ appPath, config, plugins: [
  path.join(appPath, 'scripts', 'controlled-build-plugin.cjs'),
  '@tarojs/plugin-platform-' + platform,
  '@tarojs/plugin-framework-react',
] })
await kernel.run({ name: 'build', opts: { _: ['build'], options: { platform, isWatch } } })
const expected = platform === 'h5' ? ['index.html'] : ['app.js', 'app.json', 'pages/chat/index.wxml', 'project.config.json']
if (!isWatch && expected.some(file => !fs.existsSync(path.join(output, file)))) throw new Error('Build did not produce the required target files')
