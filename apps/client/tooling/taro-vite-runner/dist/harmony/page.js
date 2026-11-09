"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.TARO_TABBAR_PAGE_PATH = exports.PAGE_SUFFIX = void 0;
const node_path_1 = __importDefault(require("node:path"));
const core_1 = require("@babel/core");
const helper_1 = require("@tarojs/helper");
const babel_plugin_import_native_component_1 = __importDefault(require("../common/babel-plugin-import-native-component"));
const babel_plugin_remove_config_1 = __importDefault(require("../common/babel-plugin-remove-config"));
const utils_1 = require("../utils");
const createFilter_1 = require("../utils/createFilter");
const map_1 = require("../utils/map");
const template_1 = require("./template");
exports.PAGE_SUFFIX = '?page-loader=true';
exports.TARO_TABBAR_PAGE_PATH = 'taro_tabbar';
const nativeComponentMapCache = new WeakMap();
const nativeUniqueKeyMap = new WeakMap();
function default_1(viteCompilerContext) {
    const name = 'taro:vite-harmony-page';
    const { taroConfig, sourceDir } = viteCompilerContext;
    const filter = (0, createFilter_1.createFilterWithCompileOptions)(taroConfig.compile, [`${sourceDir}/**`, /(?<=node_modules[\\/]).*taro/], []);
    let viteConfig;
    let nCompCache;
    let nCompUniqueKeyMap;
    return {
        name,
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
        resolveId(source, importer, options) {
            var _a;
            if (((viteCompilerContext === null || viteCompilerContext === void 0 ? void 0 : viteCompilerContext.isPage(source)) || (viteCompilerContext === null || viteCompilerContext === void 0 ? void 0 : viteCompilerContext.isComponent(source))) && options.isEntry) {
                if ((_a = viteCompilerContext.getPageById(source)) === null || _a === void 0 ? void 0 : _a.isNative)
                    return null;
                return (0, utils_1.appendVirtualModulePrefix)(source + exports.PAGE_SUFFIX);
            }
            else if (source.includes(exports.TARO_TABBAR_PAGE_PATH) && options.isEntry) {
                return (0, utils_1.appendVirtualModulePrefix)(source);
            }
            else if (source.endsWith(exports.PAGE_SUFFIX)) {
                return (0, utils_1.appendVirtualModulePrefix)(source);
            }
            else if (utils_1.virtualModulePrefixREG.test(importer || '')) {
                importer = (0, utils_1.stripVirtualModulePrefix)(importer || '');
                if (source.includes(exports.TARO_TABBAR_PAGE_PATH) && source === importer.replace(exports.PAGE_SUFFIX, '')) {
                    return (0, utils_1.appendVirtualModulePrefix)(source);
                }
                else {
                    return this.resolve(source, importer, options);
                }
            }
            return null;
        },
        load(id) {
            return __awaiter(this, void 0, void 0, function* () {
                var _a, _b, _c;
                if (!viteCompilerContext)
                    return;
                const { taroConfig, cwd: appPath, app, loaderMeta } = viteCompilerContext;
                const appConfig = app.config;
                const { sourceRoot = 'src' } = taroConfig;
                const appRoot = node_path_1.default.resolve(appPath, sourceRoot);
                const parse = new template_1.PageParser(appPath, appConfig, taroConfig, loaderMeta, taroConfig.isPure);
                const tabbarList = ((_a = appConfig.tabBar) === null || _a === void 0 ? void 0 : _a.list) || [];
                const rawId = (0, utils_1.stripVirtualModulePrefix)(id).replace(exports.PAGE_SUFFIX, '');
                if (id.endsWith(exports.PAGE_SUFFIX)) {
                    const page = viteCompilerContext.getPageById(rawId) || viteCompilerContext.getComponentById(rawId);
                    // Note: 组件编译模式下禁用 TabBar 页面生成
                    const isTabbarPage = !taroConfig.isBuildNativeComp &&
                        tabbarList.some(item => item.pagePath === (page === null || page === void 0 ? void 0 : page.name));
                    if (!page) {
                        viteCompilerContext.logger.warn(`编译页面 ${rawId} 失败!`);
                        process.exit(1);
                    }
                    if (isTabbarPage) {
                        if (tabbarList[0].pagePath === page.name) {
                            const tabbarPages = tabbarList.map(item => viteCompilerContext.pages.find((e) => {
                                if (e.name === item.pagePath) {
                                    e.originName = item.pagePath;
                                    e.id = (0, utils_1.appendVirtualModulePrefix)(e.scriptPath + exports.PAGE_SUFFIX);
                                    return true;
                                }
                            }));
                            const tabbarId = node_path_1.default.join(appRoot, `${exports.TARO_TABBAR_PAGE_PATH}`);
                            this.emitFile({
                                type: 'prebuilt-chunk',
                                fileName: viteCompilerContext.getTargetFilePath(exports.TARO_TABBAR_PAGE_PATH, '.ets'),
                                code: parse.parse(tabbarId, tabbarPages, name, this.resolve),
                                exports: ['default'],
                            });
                            yield Promise.all(tabbarPages.map((page) => __awaiter(this, void 0, void 0, function* () {
                                const deps = yield viteCompilerContext.collectedDeps(this, (0, utils_1.escapePath)(page.scriptPath), filter);
                                const ncObj = {};
                                deps.forEach(dep => {
                                    Object.entries(nCompCache.get(dep) || {}).forEach(([key, value]) => {
                                        let importPath = value[0];
                                        const ext = node_path_1.default.extname(importPath);
                                        const basename = node_path_1.default.basename(importPath, ext);
                                        if (node_path_1.default.isAbsolute(importPath)) {
                                            importPath = node_path_1.default.relative(node_path_1.default.dirname(rawId), importPath);
                                        }
                                        ncObj[key] = [node_path_1.default.join(node_path_1.default.dirname(importPath), basename), value[1]];
                                    });
                                });
                                if (!page.isNative) {
                                    page.config.usingComponents = Object.assign(Object.assign({}, page.config.usingComponents), ncObj);
                                }
                                const nativeComps = viteCompilerContext.collectNativeComponents(page);
                                nativeComps.forEach(comp => {
                                    viteCompilerContext.generateNativeComponent(this, comp, [rawId]);
                                });
                            })));
                        }
                    }
                    else {
                        const list = [];
                        const key = Object.keys(((_b = taroConfig.router) === null || _b === void 0 ? void 0 : _b.customRoutes) || {}).find(e => [page.name, (0, utils_1.addLeadingSlash)(page.name)].includes(e));
                        if (key) {
                            const alias = (_c = taroConfig.router) === null || _c === void 0 ? void 0 : _c.customRoutes[key];
                            if (alias instanceof Array) {
                                list.push(...alias);
                            }
                            else {
                                list.push(alias);
                            }
                        }
                        else {
                            list.push(page.name);
                        }
                        yield Promise.all(list.map((pageName) => __awaiter(this, void 0, void 0, function* () {
                            pageName = (0, helper_1.removeHeadSlash)(pageName);
                            if (!pageName) {
                                pageName = 'index';
                            }
                            const page_ = page;
                            page_.id = id;
                            page_.originName || (page_.originName = page.name); // Note: originName 仅更新一次, watch 模式下这里可能反复进入
                            page_.name = pageName;
                            this.emitFile({
                                type: 'prebuilt-chunk',
                                fileName: viteCompilerContext.getTargetFilePath(pageName, '.ets'),
                                code: parse.parse(node_path_1.default.resolve(appRoot, pageName), page_, name, this.resolve),
                                exports: ['default'],
                            });
                            const ncObj = {};
                            const deps = yield viteCompilerContext.collectedDeps(this, (0, utils_1.escapePath)(rawId), filter);
                            deps.forEach(dep => {
                                Object.entries(nCompCache.get(dep) || {}).forEach(([key, value]) => {
                                    let importPath = value[0];
                                    const ext = node_path_1.default.extname(importPath);
                                    const basename = node_path_1.default.basename(importPath, ext);
                                    if (node_path_1.default.isAbsolute(importPath)) {
                                        importPath = node_path_1.default.relative(node_path_1.default.dirname(rawId), importPath);
                                    }
                                    ncObj[key] = [node_path_1.default.join(node_path_1.default.dirname(importPath), basename), value[1]];
                                });
                            });
                            if (!page.isNative) {
                                page.config.usingComponents = Object.assign(Object.assign({}, page.config.usingComponents), ncObj);
                            }
                            const nativeComps = viteCompilerContext.collectNativeComponents(page);
                            nativeComps.forEach(comp => {
                                viteCompilerContext.generateNativeComponent(this, comp, [rawId]);
                            });
                        })));
                    }
                    return parse.parseEntry(rawId, page);
                }
            });
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
                            scopeNativeComp.set(key, [path, exportName]);
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