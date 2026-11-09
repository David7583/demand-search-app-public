# Local Taro Vite 6 compatibility maintenance

This is a project-maintained candidate, not an official Taro release or a claim of general Taro compatibility. Original package name is retained for Taro resolution; version is `4.3.2-dsa.1` and npm publication is disabled with `private: true`. Original O2Team MIT license and upstream notices remain unchanged. Local patches were prepared with AI assistance; no exclusive authorship over upstream material is claimed.

Exact baseline: `@tarojs/vite-runner@4.3.2`, official npm tarball SHA-256 `88453630d4f960a8461814594939e75012e333ad943f68315deb89ec7bf86d43`. Registry SHA-512 is in PATCHES.json. Registry gitHead is absent; the version tag link is a tracking reference, not an assertion that its generated files are byte-identical.

## Patch scope

- Pin Vite peer to 6.4.5, static-copy to 2.3.2, legacy plugin to 6.1.1, and replace html-minifier 4 with html-minifier-terser 7.2.0.
- Native dynamic import for asynchronous Vite build/server and ESM-only static-copy at H5, mini and Harmony entry points.
- Await XML compression in all four template call sites. Sequential page iteration preserves base-template calculation before per-page mutation. A compression error rejects the awaited bundle hook.
- Migrate two HTML hook objects to order/handler; explicitly retain the existing legacy Sass importer contract and previous mini library CSS name.
- Default H5 CORS to false instead of permitting every origin. Explicit developer configuration remains possible. Development servers are still local-only and not production services.
- Seven changed JS maps and their sourceMappingURL comments are removed because they describe original code. Original maps remain in the pinned source archive. Unmodified mappings are preserved.

Vite 6.4.5 still provides the synchronous CJS helpers used by logger, native support and H5 config. These calls remain with their deprecation warning, not a suppressed warning. A complete ESM rewrite is outside this narrow compatibility patch. Rollup 4 commonjs default changes and minified WeChat templates require actual candidate integration tests. Harmony was updated only at the shared entry import boundary and is not validated.

## Rebuild and verification

`python REBUILD.py --archive /path/to/tarojs-vite-runner-4.3.2.tgz --output /new/empty/path` verifies original SHA-256/SHA-512, path safety, each input hash, exact text replacement counts, resulting hashes, and preserved MIT text. Omit --archive to retrieve that same official URL. Existing output directories are rejected. This rebuild patches distributed JavaScript; it does not pretend to compile unprovided upstream TypeScript. The readable maintenance.patch and machine recipe include the complete change.

`node --test tests/async-template.test.mjs` exercises a synthetic minifier with delayed promises, rejection and disabled minification. It tests async completion semantics, not the real minifier implementation. Candidate H5 and weapp builds must additionally run with real html-minifier-terser and explicit mini.minifyXML.collapseWhitespace=true, inspect emitted WXML and run application regression tests.

Before adoption require strict-peer installation, full npm audit (including dev), reproducible rebuild equality, H5/weapp builds, live dev copy/plugin tests on isolated loopback ports, path-denial checks, and existing frontend/browser tests. No production-safety or security-clearance conclusion follows from this source patch alone.

## Upstream tracking

- https://github.com/NervJS/taro/tree/v4.3.2/packages/taro-vite-runner
- https://v5.vite.dev/guide/migration.html
- https://v6.vite.dev/guide/migration.html
- https://registry.npmjs.org/vite-plugin-static-copy/2.3.2
- https://github.com/terser/html-minifier-terser

No issue, pull request or public fork has been created. Monitor Taro's peer ranges, emitter async API and secure compiler dependencies; retire this maintenance patch when a supported upstream release passes the same tests.
