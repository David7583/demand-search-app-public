"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = (id = '') => {
    return function pluginRemovePageConfig(babel) {
        const { types: t } = babel;
        return {
            name: 'plugin:remove_pageconfig',
            visitor: {
                CallExpression(nodePath, state) {
                    if (!/\.config\.(t|j)sx?$/.test(state.filename || id))
                        return;
                    const { callee } = nodePath.node;
                    if (!t.isIdentifier(callee))
                        return;
                    if (!['defineAppConfig', 'definePageConfig'].includes(callee.name))
                        return;
                    nodePath.remove();
                }
            }
        };
    };
};
//# sourceMappingURL=babel-plugin-remove-config.js.map