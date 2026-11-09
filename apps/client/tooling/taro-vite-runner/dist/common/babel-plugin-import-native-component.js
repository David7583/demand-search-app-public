"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_path_1 = __importDefault(require("node:path"));
const helper_1 = require("@tarojs/helper");
const IMPORT_COMPONENT_NAME = 'importNativeComponent';
exports.default = (compiler, id, cb) => {
    return function pluginImportNativeComponent(babel) {
        const t = babel.types;
        let enableImportComponent = true;
        return {
            name: 'plugin:import-native-component',
            visitor: {
                CallExpression(ast) {
                    // 识别所有 importNativeComponent 函数调用, 并替换为对应的组件名
                    if (t.isIdentifier(ast.node.callee, { name: IMPORT_COMPONENT_NAME })) {
                        let pathArg = compiler.resolvePageImportPath(id, t.isStringLiteral(ast.node.arguments[0]) ? ast.node.arguments[0].value : '');
                        if (pathArg.startsWith('.')) {
                            pathArg = node_path_1.default.resolve(node_path_1.default.dirname(id), pathArg);
                        }
                        pathArg = (0, helper_1.resolveMainFilePath)(pathArg);
                        const nameArg = t.isStringLiteral(ast.node.arguments[1]) ? ast.node.arguments[1].value : '';
                        const exportNameArg = t.isStringLiteral(ast.node.arguments[2]) ? ast.node.arguments[2].value : 'default';
                        if (enableImportComponent) {
                            const nativeName = cb(pathArg, nameArg, exportNameArg);
                            ast.replaceWith(t.stringLiteral(nativeName));
                        }
                    }
                },
                FunctionDeclaration(ast) {
                    if (t.isIdentifier(ast.node.id, { name: IMPORT_COMPONENT_NAME })) {
                        enableImportComponent = false;
                        cb(false);
                    }
                },
                ImportDeclaration(ast) {
                    ast.node.specifiers.forEach(specifier => {
                        if ((t.isImportSpecifier(specifier) || t.isImportDefaultSpecifier(specifier)) &&
                            specifier.local.name === IMPORT_COMPONENT_NAME) {
                            enableImportComponent = false;
                            cb(false);
                        }
                    });
                },
                VariableDeclarator(ast) {
                    if (t.isIdentifier(ast.node.id, { name: IMPORT_COMPONENT_NAME }) &&
                        (t.isArrowFunctionExpression(ast.node.init) ||
                            t.isFunctionExpression(ast.node.init))) {
                        enableImportComponent = false;
                        cb(false);
                    }
                }
            }
        };
    };
};
//# sourceMappingURL=babel-plugin-import-native-component.js.map