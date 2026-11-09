export default function createFilter(include: any, exclude: any, options?: any): (id: any) => boolean;
export declare function createFilterWithCompileOptions(compile?: {
    exclude?: any[];
    include?: any[];
    /** 对应 @rollup/plugin-babel 插件的 filter 配置。只在 vite 编译模式下有效 */
    filter?: (filename: string) => boolean;
}, defaultInclude?: any[], defaultExclude?: any[]): (id: any) => boolean;
