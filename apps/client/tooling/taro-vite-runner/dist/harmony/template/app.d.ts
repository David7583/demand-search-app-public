import BaseParser from './base';
import type { AppConfig } from '@tarojs/taro';
import type { TRollupResolveMethod } from '@tarojs/taro/types/compile/config/plugin';
import type { ViteAppMeta, ViteHarmonyBuildConfig } from '@tarojs/taro/types/compile/viteCompilerContext';
export interface TaroHarmonyAppMeta extends ViteAppMeta {
    modifyAppImport?: (this: Parser, importStr: string[], config: TaroHarmonyAppMeta) => void;
}
export default class Parser extends BaseParser {
    #private;
    protected appPath: string;
    protected appConfig: AppConfig;
    protected buildConfig: ViteHarmonyBuildConfig;
    protected loaderMeta: Record<string, unknown>;
    constructor(appPath: string, appConfig: AppConfig, buildConfig: ViteHarmonyBuildConfig, loaderMeta: Record<string, unknown>);
    init(): void;
    getInitPxTransform(): any;
    get instantiateApp(): string;
    parse(rawId: string, app: TaroHarmonyAppMeta, resolve?: TRollupResolveMethod): string;
    parseEntry(rawId: string, app: TaroHarmonyAppMeta): any;
}
