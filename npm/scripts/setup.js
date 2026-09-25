#!/usr/bin/env node
"use strict";
// postinstall: creates a private venv inside this npm package's own
// install directory and installs the vendored Python source into it.
// Never touches the user's system/global Python -- brainstem's own venv
// lives entirely under this package's node_modules entry.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PKG_ROOT = path.resolve(__dirname, "..");
const VENDOR_DIR = path.join(PKG_ROOT, "vendor");
const VENV_DIR = path.join(PKG_ROOT, ".venv");

function commandVersion(cmd) {
  // Deliberately not routed through `where`/`which`: on at least one
  // real tested environment (Git Bash on Windows spawning this postinstall
  // via npm), the Node process's PATH doesn't include System32, so `where`
  // itself is unresolvable (ENOENT) even though `uv`/`python` are perfectly
  // reachable directly -- `where`/`which` were an unnecessary, less
  // portable indirection. Invoking the target command itself is what
  // Node's own PATH-search child_process resolution is actually good at.
  const result = spawnSync(cmd, ["--version"], { encoding: "utf8" });
  if (result.error || result.status !== 0) {
    return null;
  }
  return `${result.stdout || ""}${result.stderr || ""}`.trim();
}

function compatiblePython(cmd) {
  const version = commandVersion(cmd);
  const match = version && version.match(/Python\s+(\d+)\.(\d+)/i);
  if (!match) {
    return false;
  }
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major > 3 || (major === 3 && minor >= 11);
}

function run(cmd, args, options = {}) {
  console.log(`> ${cmd} ${args.join(" ")}`);
  const result = spawnSync(cmd, args, { stdio: "inherit", ...options });
  if (result.status !== 0) {
    throw new Error(`${cmd} ${args.join(" ")} exited with code ${result.status}`);
  }
}

function venvPythonPath() {
  return process.platform === "win32"
    ? path.join(VENV_DIR, "Scripts", "python.exe")
    : path.join(VENV_DIR, "bin", "python");
}

function main() {
  if (!fs.existsSync(VENDOR_DIR)) {
    console.error(
      "setup: vendor/ is missing from this package -- it should have been " +
        "created by `npm run sync-vendor` before packaging/publishing."
    );
    process.exit(1);
  }

  const haveUv = commandVersion("uv") !== null;
  const pythonCmd = compatiblePython("python3")
    ? "python3"
    : compatiblePython("python")
      ? "python"
      : null;

  if (!haveUv && !pythonCmd) {
    console.error(
      "\nbrainstem requires uv on PATH for a verified installation: https://docs.astral.sh/uv/\n" +
        "Install uv, then re-run: npm install -g @faizalmunna/brainstem\n"
    );
    process.exit(1);
  }

  if (!haveUv && process.env.BRAINSTEM_ALLOW_UNVERIFIED_PIP !== "1") {
    console.error(
      "\nbrainstem requires uv on PATH for a verified installation. uv sync installs the reviewed, " +
        "locked dependency graph shipped in this package.\n" +
        "Install uv (https://docs.astral.sh/uv/) and re-run npm install.\n" +
        "For an emergency legacy pip install only, set BRAINSTEM_ALLOW_UNVERIFIED_PIP=1 explicitly.\n"
    );
    process.exit(1);
  }

  try {
    if (haveUv) {
      // uv can locate or download a compatible interpreter. Pinning this
      // avoids creating an environment from an unsupported system Python.
      run("uv", ["venv", "--python", "3.11", VENV_DIR]);
      // `--active` directs the project sync to this package's private venv
      // rather than creating vendor/.venv. `--locked` makes the installed
      // runtime graph exactly match the reviewed uv.lock shipped in vendor/.
      run(
        "uv",
        ["sync", "--project", VENDOR_DIR, "--active", "--locked", "--no-dev"],
        { env: { ...process.env, VIRTUAL_ENV: VENV_DIR } }
      );
    } else {
      // This is deliberately opt-in. pip resolves the loose runtime
      // constraints in pyproject.toml rather than the reviewed uv.lock, so it
      // cannot make the same supply-chain guarantee as the default path.
      console.warn("WARNING: using explicitly requested unverified pip fallback.");
      run(pythonCmd, ["-m", "venv", VENV_DIR]);
      run(venvPythonPath(), ["-m", "pip", "install", "--upgrade", "pip"]);
      run(venvPythonPath(), ["-m", "pip", "install", VENDOR_DIR]);
    }
  } catch (err) {
    console.error(`\nbrainstem failed to finish installing its Python dependency:\n${err.message}\n`);
    process.exit(1);
  }

  console.log("\nbrainstem is ready. Run `brainstem --help` to get started.\n");
}

main();
