"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.PAGE_SUFFIX = void 0;
const node_path_1 = __importDefault(require("node:path"));
const core_1 = require("@babel/core");
const babel_plugin_import_native_component_1 = __importDefault(require("../common/babel-plugin-import-native-component"));
const babel_plugin_remove_config_1 = __importDefault(require("../common/babel-plugin-remove-config"));
const utils_1 = require("../utils");
const createFilter_1 = require("../utils/createFilter");
const map_1 = require("../utils/map");
exports.PAGE_SUFFIX = '?page-loader=true';
const nativeComponentMapCache = new WeakMap();
const nativeUniqueKeyMap = new WeakMap();
function default_1(viteCompilerContext) {
    const { taroConfig, sourceDir } = viteCompilerContext;
    const filter = (0, createFilter_1.createFilterWithCompileOptions)(taroConfig.compile, [sourceDir, /(?<=node_modules[\\/]).*taro/], []);
    let viteConfig;
    let nCompCache;
    let nCompUniqueKeyMap;
    return {
        name: 'taro:vite-mini-page',
        enforce: 'pre',
        configResolved(config) {
            viteConfig = config;
        },
        buildStart() {
            if (nativeComponentMapCache.has(viteConfig)) {
                nCompCache = nativeComponentMapCache.get(viteConfig);
                nCompUniqueKeyMap = nativeUniqueKeyMap.get(viteConfig);
            }
            else {
                nCompCache = new Map();
                nativeComponentMapCache.set(viteConfig, nCompCache);
                nCompUniqueKeyMap = new map_1.UniqueKeyMap();
                nativeUniqueKeyMap.set(viteConfig, nCompUniqueKeyMap);
            }
        },
        resolveId(source, _importer, options) {
            var _a;
            if ((viteCompilerContext === null || viteCompilerContext === void 0 ? void 0 : viteCompilerContext.isPage(source)) && options.isEntry) {
                if ((_a = viteCompilerContext.getPageById(source)) === null || _a === void 0 ? void 0 : _a.isNative)
                    return null;
                return (0, utils_1.appendVirtualModulePrefix)(source + exports.PAGE_SUFFIX);
            }
            return null;
        },
        load(id) {
            if (viteCompilerContext && id.endsWith(exports.PAGE_SUFFIX)) {
                const rawId = (0, utils_1.stripVirtualModulePrefix)(id).replace(exports.PAGE_SUFFIX, '');
                const page = viteCompilerContext.getPageById(rawId);
                if (!page) {
                    viteCompilerContext.logger.warn(`编译页面 ${rawId} 失败!`);
                    process.exit(1);
                }
                const pageConfig = (0, utils_1.prettyPrintJson)(page.config);
                const isCustomTabBar = page.name === 'custom-tab-bar/index';
                let instantiatePage = isCustomTabBar
                    ? `var inst = Component(createComponentConfig(component, '${page.name}', {root:{cn:[]}}))`
                    : `var inst = Page(createPageConfig(component, '${page.name}', {root:{cn:[]}}, config || {}))`;
                if (typeof viteCompilerContext.loaderMeta.modifyInstantiate === 'function') {
                    instantiatePage = viteCompilerContext.loaderMeta.modifyInstantiate(instantiatePage, 'page');
                }
                viteCompilerContext.collectedDeps(this, (0, utils_1.escapePath)(rawId), filter).then(deps => {
                    const ncObj = {};
                    deps.forEach(dep => {
                        Object.entries(nCompCache.get(dep) || {}).forEach(([key, value]) => {
                            const absPath = value;
                            const ext = node_path_1.default.extname(absPath);
                            const basename = node_path_1.default.basename(absPath, ext);
                            ncObj[key] = node_path_1.default.join(node_path_1.default.dirname(node_path_1.default.relative(node_path_1.default.dirname(rawId), absPath)), basename);
                        });
                    });
                    if (!page.isNative) {
                        page.config.usingComponents = Object.assign(Object.assign({}, page.config.usingComponents), ncObj);
                    }
                    const nativeComps = viteCompilerContext.collectNativeComponents(page);
                    nativeComps.forEach(comp => {
                        viteCompilerContext.generateNativeComponent(this, comp, [rawId]);
                    });
                });
                return [
                    isCustomTabBar
                        ? 'import { createComponentConfig } from "@tarojs/runtime"'
                        : 'import { createPageConfig } from "@tarojs/runtime"',
                    `import component from "${(0, utils_1.escapePath)(rawId)}"`,
                    `var config = ${pageConfig}`,
                    page.config.enableShareTimeline ? 'component.enableShareTimeline = true' : '',
                    page.config.enableShareAppMessage ? 'component.enableShareAppMessage = true' : '',
                    instantiatePage,
                ].join('\n');
            }
        },
        transform(code, id) {
            if (/\.m?[jt]sx?$/.test(id) && filter(id)) {
                const scopeNativeComp = new Map();
                let enableImportComponent = true;
                const result = (0, core_1.transformSync)(code, {
                    filename: id,
                    parserOpts: {
                        plugins: [
                            'jsx',
                            'typescript',
                        ],
                    },
                    plugins: [
                        (0, babel_plugin_remove_config_1.default)(id),
                        (0, babel_plugin_import_native_component_1.default)(viteCompilerContext, id, (path, name = '', exportName = '') => {
                            if (path === false) {
                                enableImportComponent = false;
                                return '';
                            }
                            let key = `${name}${exportName !== 'default' ? `_${exportName}` : ''}`.toLowerCase();
                            key = nCompUniqueKeyMap.add(key, path);
                            scopeNativeComp.set(key, path);
                            return key;
                        }),
                    ]
                });
                if (enableImportComponent) {
                    nCompCache.set(id, Object.fromEntries(scopeNativeComp));
                    return {
                        code: (result === null || result === void 0 ? void 0 : result.code) || code,
                        map: (result === null || result === void 0 ? void 0 : result.map) || null,
                    };
                }
            }
        }
    };
}
exports.default = default_1;
//# sourceMappingURL=page.js.map