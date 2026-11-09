"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const vite_plugin_assets_1 = __importDefault(require("../common/vite-plugin-assets"));
const vite_plugin_multi_platform_1 = __importDefault(require("../common/vite-plugin-multi-platform"));
const config_1 = __importDefault(require("./config"));
const emit_1 = __importDefault(require("./emit"));
const entry_1 = __importDefault(require("./entry"));
const native_support_1 = __importDefault(require("./native-support"));
const page_1 = __importDefault(require("./page"));
const pipeline_1 = __importDefault(require("./pipeline"));
const style_1 = __importDefault(require("./style"));
function default_1(viteCompilerContext) {
    return [
        (0, pipeline_1.default)(viteCompilerContext),
        (0, config_1.default)(viteCompilerContext),
        (0, entry_1.default)(viteCompilerContext),
        (0, page_1.default)(viteCompilerContext),
        (0, vite_plugin_multi_platform_1.default)(viteCompilerContext),
        (0, native_support_1.default)(viteCompilerContext),
        (0, vite_plugin_assets_1.default)(viteCompilerContext),
        (0, style_1.default)(viteCompilerContext),
        (0, emit_1.default)(viteCompilerContext),
    ];
}
exports.default = default_1;
//# sourceMappingURL=index.js.map