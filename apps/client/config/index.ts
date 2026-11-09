import type { IProjectConfig } from '@tarojs/taro/types/compile'

export default {
  projectName: 'demand-search-app',
  date: '2026-11-04',
  designWidth: 750,
  deviceRatio: { 640: 2.34 / 2, 750: 1, 828: 1.81 / 2 },
  sourceRoot: 'src',
  outputRoot: process.env.DSA_CLIENT_BUILD === 'staging' ? `../../.local/s2-client/${process.env.TARO_ENV ?? 'h5'}` : `dist/${process.env.TARO_ENV ?? 'h5'}`,
  framework: 'react',
  compiler: { type: 'vite' },
  cache: { enable: false },
  mini: { postcss: { pxtransform: { enable: false }, cssModules: { enable: false } } },
  h5: {
    publicPath: '/',
    router: { mode: 'hash' },
    devServer: { host: '127.0.0.1', port: 10086 },
    postcss: { pxtransform: { enable: false }, autoprefixer: { enable: true } },
  },
} satisfies IProjectConfig<'vite'>
