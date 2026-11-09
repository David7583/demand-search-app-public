# Local compatibility maintenance fork

Based on @tarojs/plugin-framework-react 4.3.2 from the official npm tarball.
Original package name, MIT license and copyright are retained. This is not an upstream release.
Runtime code is unchanged. The Vite peer is explicitly moved to 6.4.5; this declaration alone
is not evidence of compatibility or security. Candidate D must pass real builds, browser
and security regressions before adoption. No global peer-ignore flag is allowed.
See UPSTREAM-MAINTENANCE.json for original integrity and exact changes.

Rebuild from the exact original archive with: python REBUILD.py --archive /path/to/plugin-framework-react-4.3.2.tgz --output /new/path
The script verifies original SHA-256/SHA-512 and exact input/output file hashes. Existing output paths are refused.
PATCHES.json and maintenance.patch record the complete metadata-only change. Runtime JS, maps and MIT text are unchanged.
No upstream issue/PR or endorsement is claimed. Track https://github.com/NervJS/taro/tree/v4.3.2/packages/taro-plugin-framework-react .
The npm registry does not supply a gitHead for this release; archive hashes identify the precise baseline. Local metadata maintenance was AI-assisted.
