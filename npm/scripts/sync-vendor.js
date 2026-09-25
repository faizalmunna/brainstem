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
const crypto = require("crypto");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const VENDOR_DIR = path.resolve(__dirname, "..", "vendor");

const EXCLUDE_DIRS = new Set([".venv", ".git", ".brain", "__pycache__", "node_modules", ".pytest_cache"]);

function shouldSkip(src) {
  const base = path.basename(src);
  return EXCLUDE_DIRS.has(base);
}

function copyTree(src, dest) {
  if (shouldSkip(src)) {
    return;
  }
  const stat = fs.lstatSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
      copyTree(path.join(src, entry.name), path.join(dest, entry.name));
    }
    return;
  }
  if (!stat.isFile()) {
    throw new Error(`sync-vendor: unsupported source entry: ${src}`);
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function fileDigests(root) {
  const results = new Map();
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const current = path.join(directory, entry.name);
      if (shouldSkip(current)) {
        continue;
      }
      if (entry.isDirectory()) {
        visit(current);
      } else if (entry.isFile()) {
        const relative = path.relative(root, current).split(path.sep).join("/");
        results.set(relative, crypto.createHash("sha256").update(fs.readFileSync(current)).digest("hex"));
      } else {
        throw new Error(`sync-vendor: unsupported source entry: ${current}`);
      }
    }
  }
  visit(root);
  return results;
}

function assertExactCopy(src, dest) {
  const expected = fileDigests(src);
  const actual = fileDigests(dest);
  const mismatches = [];
  for (const [relative, digest] of expected) {
    if (actual.get(relative) !== digest) {
      mismatches.push(relative);
    }
  }
  for (const relative of actual.keys()) {
    if (!expected.has(relative)) {
      mismatches.push(relative);
    }
  }
  if (mismatches.length) {
    throw new Error(
      `sync-vendor: integrity verification failed for ${src}; ` +
      `${mismatches.length} file(s) differ (first: ${mismatches.slice(0, 5).join(", ")})`
    );
  }
  return expected.size;
}

function copy(relPath) {
  const src = path.join(REPO_ROOT, relPath);
  const dest = path.join(VENDOR_DIR, relPath);
  if (!fs.existsSync(src)) {
    throw new Error(`sync-vendor: required source is missing: ${relPath}`);
  }
  copyTree(src, dest);
  return fs.lstatSync(src).isDirectory() ? assertExactCopy(src, dest) : 1;
}

fs.rmSync(VENDOR_DIR, { recursive: true, force: true });
fs.mkdirSync(VENDOR_DIR, { recursive: true });

// The lockfile travels with the source so `uv` installs made by the npm
// wrapper resolve the exact dependency graph tested by this repository.
let copiedFiles = 0;
for (const item of ["src", "pyproject.toml", "uv.lock", "LICENSE", "README.md"]) {
  copiedFiles += copy(item);
}

console.log(`sync-vendor: integrity-verified ${copiedFiles} files in ${VENDOR_DIR}`);
