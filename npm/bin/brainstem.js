#!/usr/bin/env node
"use strict";
// Launcher shim: forwards to the real brainstem CLI, installed into this
// package's own private venv by scripts/setup.js at install time.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PKG_ROOT = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PKG_ROOT, ".venv");

function venvBinary() {
  return process.platform === "win32"
    ? path.join(VENV_DIR, "Scripts", "brainstem.exe")
    : path.join(VENV_DIR, "bin", "brainstem");
}

const binPath = venvBinary();
if (!fs.existsSync(binPath)) {
  console.error(
    "brainstem: the Python environment hasn't been set up yet.\n" +
      "Try reinstalling: `npm install -g @faizalmunna/brainstem` (this runs setup automatically)."
  );
  process.exit(1);
}

const result = spawnSync(binPath, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status === null ? 1 : result.status);
