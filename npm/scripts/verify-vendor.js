#!/usr/bin/env node
"use strict";
// Verifies the manifest created by sync-vendor before postinstall executes
// uv against vendored Python source. This is intentionally dependency-free.

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const INTEGRITY_FILE = ".brainstem-integrity.json";

function fileDigests(root) {
  const results = new Map();
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (entry.name === INTEGRITY_FILE) {
        continue;
      }
      const current = path.join(directory, entry.name);
      const stat = fs.lstatSync(current);
      if (stat.isDirectory()) {
        visit(current);
      } else if (stat.isFile()) {
        const relative = path.relative(root, current).split(path.sep).join("/");
        results.set(relative, crypto.createHash("sha256").update(fs.readFileSync(current)).digest("hex"));
      } else {
        throw new Error(`vendor integrity: unsupported entry: ${current}`);
      }
    }
  }
  visit(root);
  return results;
}

function verifyVendorIntegrity(vendorDir) {
  const manifestPath = path.join(vendorDir, INTEGRITY_FILE);
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (err) {
    throw new Error(`vendor integrity: unable to read ${INTEGRITY_FILE}: ${err.message}`);
  }
  if (
    !manifest ||
    manifest.schema_version !== 1 ||
    manifest.algorithm !== "sha256" ||
    !manifest.files ||
    typeof manifest.files !== "object" ||
    Array.isArray(manifest.files)
  ) {
    throw new Error("vendor integrity: invalid manifest schema");
  }
  const expected = new Map(Object.entries(manifest.files));
  const actual = fileDigests(vendorDir);
  if (expected.size === 0 || expected.size !== actual.size) {
    throw new Error("vendor integrity: file set does not match manifest");
  }
  for (const [relative, digest] of expected) {
    if (!/^[0-9a-f]{64}$/.test(digest) || actual.get(relative) !== digest) {
      throw new Error(`vendor integrity: digest mismatch for ${relative}`);
    }
  }
  return expected.size;
}

module.exports = { verifyVendorIntegrity };

if (require.main === module) {
  try {
    const vendorDir = path.resolve(__dirname, "..", "vendor");
    console.log(`vendor integrity: verified ${verifyVendorIntegrity(vendorDir)} files`);
  } catch (err) {
    console.error(err.message);
    process.exitCode = 1;
  }
}
