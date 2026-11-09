'use strict';

// Derived from globs 0.1.4 (MIT). See LICENSE, UPSTREAM.json and README-FORK.md.
// Use the official unbundled entry so the lockfile describes executed dependencies.
const { glob, globSync } = require('glob/raw');

const forwarded = new Set([
  'cwd', 'root', 'dot', 'mark', 'nobrace', 'noglobstar', 'noext',
  'nocase', 'matchBase', 'nodir', 'ignore', 'follow', 'realpath', 'absolute',
  'signal', 'fs',
]);
const MAX_PATTERNS = 256;
const MAX_PATTERN_LENGTH = 4096;

function failure(code, message) {
  const error = new TypeError(message);
  error.code = code;
  return error;
}

function normalize(patterns, options) {
  const list = Array.isArray(patterns) ? patterns.slice() : [patterns];
  if (list.length > MAX_PATTERNS) {
    throw failure('GLOBS_PATTERN_LIMIT', 'At most 256 glob patterns are supported.');
  }
  for (const pattern of list) {
    if (typeof pattern !== 'string') {
      throw failure('GLOBS_PATTERN_TYPE', 'Each glob pattern must be a string.');
    }
    if (pattern.length > MAX_PATTERN_LENGTH) {
      throw failure('GLOBS_PATTERN_LIMIT', 'A glob pattern may contain at most 4096 UTF-16 code units.');
    }
  }
  if (options == null) options = {};
  if (typeof options !== 'object' || Array.isArray(options)) {
    throw failure('GLOBS_OPTIONS_TYPE', 'Glob options must be an object.');
  }
  const modern = {
    // glob 7 treated Windows backslashes as path separators.
    windowsPathsNoEscape: process.platform === 'win32',
    braceExpandMax: 10000,
  };
  for (const key of Object.keys(options)) {
    if (key === 'nosort') continue;
    if (!forwarded.has(key)) {
      throw failure('GLOBS_UNSUPPORTED_OPTION', 'Unsupported legacy glob option: ' + key);
    }
    modern[key] = options[key];
  }
  return { list, modern, nosort: !!options.nosort };
}

function perPattern(pattern, modern) {
  return { ...modern, ...(modern.realpath ? { absolute: true } : {}), dotRelative: /^\.\//.test(pattern.replace(/\\/g, '/')) };
}

function ordered(files, nosort, realpath) {
  if (process.platform === 'win32' && !realpath) files = files.map(file => file.replace(/\\/g, '/'));
  return nosort ? files : files.sort((a, b) => a.localeCompare(b, 'en'));
}

function globs(patterns, options, callback) {
  if (typeof options === 'function') {
    callback = options;
    options = {};
  }
  if (typeof callback !== 'function') {
    throw failure('GLOBS_CALLBACK_TYPE', 'A callback function is required.');
  }
  let prepared;
  try {
    prepared = normalize(patterns, options);
  } catch (error) {
    return process.nextTick(() => callback(error, []));
  }
  const { list, modern, nosort } = prepared;
  let pending = list.length;
  let finished = false;
  let groups = [];
  if (!pending) return process.nextTick(() => callback(null, []));
  for (const pattern of list) {
    Promise.resolve().then(() => glob(pattern, perPattern(pattern, modern))).then(
      (files) => {
        if (finished) return;
        // Preserve upstream completion order and duplicates across patterns.
        groups = groups.concat(ordered(files, nosort, modern.realpath));
        if (--pending === 0) {
          finished = true;
          callback(null, groups);
        }
      },
      (error) => {
        if (finished) return;
        finished = true;
        // scss-bundle 3.1.2 reads files after rejecting; [] avoids an unrelated
        // TypeError without hiding the original error from its Promise.
        callback(error, []);
      },
    );
  }
}

globs.sync = function (patterns, options) {
  const { list, modern, nosort } = normalize(patterns, options);
  let groups = [];
  for (const pattern of list) {
    groups = groups.concat(ordered(globSync(pattern, perPattern(pattern, modern)), nosort, modern.realpath));
  }
  return groups;
};

module.exports = globs;
