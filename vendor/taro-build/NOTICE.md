# Taro build adapter provenance

The controlled build hooks in apps/client/scripts/controlled-build-plugin.cjs
and build.mjs follow the MIT-licensed Taro 4.3.2 CLI/service contract:
https://github.com/NervJS/taro/tree/v4.3.2/packages/taro-cli/src/presets

Upstream copyright: 2018 O2Team. The accompanying LICENSE was preserved from
the exact installed @tarojs/service@4.3.2 distribution. The application-specific
adapter restricts commands, plugins and output paths and omits project creation,
template downloads, Git cloning, global configuration and update checks.
No claim is made that this is a complete or officially supported Taro CLI replacement.
Original upstream rights remain with their holders. Application-original material is separately licensed as described in LICENSE-STATUS.md; this upstream MIT notice remains unchanged in scope.
