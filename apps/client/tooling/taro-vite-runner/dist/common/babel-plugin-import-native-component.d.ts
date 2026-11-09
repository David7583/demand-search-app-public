import type * as BabelCore from '@babel/core';
import type { ViteHarmonyCompilerContext, ViteMiniCompilerContext } from '@tarojs/taro/types/compile/viteCompilerContext';
type TCallback = (path: string | false, name?: string, exportName?: string) => string;
declare const _default: (compiler: ViteHarmonyCompilerContext | ViteMiniCompilerContext, id: string, cb: TCallback) => (babel: typeof BabelCore) => BabelCore.PluginObj<BabelCore.PluginPass>;
export default _default;
