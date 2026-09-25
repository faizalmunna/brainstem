#!/usr/bin/env node
"use strict";
// Copies the real Python implementation into npm/vendor/ so the npm
// package is self-contained once published -- npm only ships what's
// inside the package directory (per `files` in package.json), so a
// published package can't reach ../../src on someone else's machine.
// This script exists specifically so that's true even for a real
// `npm publish`, not just for local testing from inside this monorepo.

const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const VENDOR_DIR = path.resolve(__dirname, "..", "vendor");

const EXCLUDE_DIRS = new Set([".venv", ".git", ".brain", "__pycache__", "node_modules", ".pytest_cache"]);

function shouldSkip(src) {
  const base = path.basename(src);
  return EXCLUDE_DIRS.has(base);
}

function copy(relPath) {
  const src = path.join(REPO_ROOT, relPath);
  const dest = path.join(VENDOR_DIR, relPath);
  if (!fs.existsSync(src)) {
    console.warn(`sync-vendor: skipping missing ${relPath}`);
    return;
  }
  fs.cpSync(src, dest, {
    recursive: true,
    filter: (s) => !shouldSkip(s),
  });
}

fs.rmSync(VENDOR_DIR, { recursive: true, force: true });
fs.mkdirSync(VENDOR_DIR, { recursive: true });

// The lockfile travels with the source so `uv` installs made by the npm
// wrapper resolve the exact dependency graph tested by this repository.
for (const item of ["src", "pyproject.toml", "uv.lock", "LICENSE", "README.md"]) {
  copy(item);
}

console.log(`sync-vendor: vendored Python source into ${VENDOR_DIR}`);
