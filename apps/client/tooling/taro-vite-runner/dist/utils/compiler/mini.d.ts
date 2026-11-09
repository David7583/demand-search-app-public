import { CompilerContext } from './base';
import type { ViteAppMeta, ViteFileType, ViteMiniBuildConfig, ViteMiniCompilerContext, ViteNativeCompMeta, VitePageMeta } from '@tarojs/taro/types/compile/viteCompilerContext';
import type { PluginContext } from 'rollup';
export declare class TaroCompilerContext extends CompilerContext<ViteMiniBuildConfig> implements ViteMiniCompilerContext {
    fileType: ViteFileType;
    commonChunks: string[];
    nativeComponents: Map<string, ViteNativeCompMeta>;
    constructor(appPath: string, taroConfig: ViteMiniBuildConfig);
    processConfig(): void;
    getCommonChunks(): string[];
    compilePage: (pageName: string) => VitePageMeta;
    collectCustomTabBar(): void;
    resolvePageImportPath(scriptPath: string, importPath: string): string;
    collectNativeComponents(meta: ViteAppMeta | VitePageMeta | ViteNativeCompMeta): ViteNativeCompMeta[];
    generateNativeComponent(rollupCtx: PluginContext, meta: ViteNativeCompMeta, implicitlyLoadedAfterOneOf?: string[]): void;
    computeForceCustomWrapper(): boolean;
    /** 工具函数 */
    getScriptPath(filePath: string): string;
    getTemplatePath(filePath: string): string;
    getStylePath(filePath: string): string;
    getConfigPath(filePath: string): string;
}
