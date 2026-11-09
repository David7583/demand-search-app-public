# globs compatibility fork for Demand Search App

This is **globs 0.1.4-dsa.1**, a local MIT fork of Stephen Mathieson's globs 0.1.4. It is not an upstream release, and it is not an NCP protocol component. Original attribution and MIT terms are retained in Readme.md and LICENSE. Maintenance changes were prepared with AI assistance.

The runtime dependency really changes from glob ^7.1.1 to glob **14.0.3**. The implementation adapts the official `glob/raw` Promise and sync exports to the old callback API; the raw export avoids hiding executed dependencies inside glob's prebuilt bundle. The project's lockfile must pin the transitive dependencies; the isolated candidate uses minimatch 11.0.4.

Preserved behavior tested against the installed upstream implementation: single string and arrays, optional options argument, asynchronous callback, empty list, per-pattern English locale sorting, sync pattern order, async completion order, duplicates across patterns, no-match empty result, common glob options, Windows separators, and real SCSS bundling/deduplication. Passing an array directly to modern glob would deduplicate results across patterns and is deliberately avoided.

Explicit changes:
- The callback is called once on success or error. Error callbacks receive the original error and an empty array. This also prevents an unrelated scss-bundle error-path crash after its Promise rejects.
- At most 256 patterns, each at most 4096 UTF-16 code units. Over-limit input fails with GLOBS_PATTERN_LIMIT; it is never truncated. These bounded build-tool inputs are not application search or conversation data.
- Forwarded options: cwd, root, dot, mark, nobrace, noglobstar, noext, nocase, matchBase, nodir, ignore, follow, realpath, absolute, fs; nosort is handled locally. signal is additive.
- Cache/Glob-instance mutation options, nonull, nounique, nomount, maxLength, strict/silent, and other unlisted options are explicitly rejected with GLOBS_UNSUPPORTED_OPTION instead of silently changing their meaning. scss-bundle 3.1.2 does not pass any options, and Taro runner-utils 4.3.2 calls bundle without dedupe patterns; the regression still covers the dedupe API.
- New glob semantics apply outside the documented compatibility surface; this is not a claim of complete glob 7 compatibility. No CLI shell command is exposed.

Rebuild: verify the official globs 0.1.4 tarball against UPSTREAM.json, extract it safely, then apply globs-0.1.4-to-dsa.1.patch to index.js/index.d.ts/package.json. Readme.md is copied byte-for-byte. LICENSE is the full MIT section of that README. This README and UPSTREAM.json document the local fork; neither replaces original ownership.

Security regressions use synthetic files and externally bounded child processes. Passing them is evidence for the tested patterns and advisory fixes, not a guarantee against all denial of service inputs. Main app H5/weapp builds and the full dependency audit remain separate integration gates.
