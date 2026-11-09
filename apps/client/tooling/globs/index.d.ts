import type { GlobOptionsWithFileTypesFalse } from "glob";

declare namespace globs {
  type Options = Pick<GlobOptionsWithFileTypesFalse,
    "cwd" | "root" | "dot" | "mark" | "nobrace" | "noglobstar" | "noext" |
    "nocase" | "matchBase" | "nodir" | "ignore" | "follow" | "realpath" |
    "absolute" | "signal" | "fs"> & { nosort?: boolean };
  type Callback = (error: Error | null, matches: string[]) => void;
  function sync(patterns: string | string[], options?: Options): string[];
}
declare function globs(patterns: string | string[], callback: globs.Callback): void;
declare function globs(patterns: string | string[], options: globs.Options, callback: globs.Callback): void;
export = globs;
