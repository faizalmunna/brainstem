---
name: context-isolation-disabled-exposes-node-to-renderer
description: An Electron application has context isolation and node integration configured insecurely, allowing web content loaded in a renderer to access powerful Node.js APIs directly.
triggers: ["electron nodeintegration security risk", "context isolation disabled electron", "renderer has full node access", "electron remote module security issue"]
permissions: ["READ"]
---

## Symptom

A security review of an Electron application (or a real incident
involving unexpected code execution from web content) finds that a
renderer process has `nodeIntegration` enabled and `contextIsolation`
disabled, meaning any web content loaded in that renderer -- including
potentially untrusted content from a remote URL, an ad, or injected
content via an XSS vulnerability -- has direct access to Node.js APIs
like `fs`, `child_process`, and the ability to run arbitrary system
commands.

## Likely causes

- **`nodeIntegration: true` and `contextIsolation: false` were set early
  in development for convenience** (making it easy for renderer code to
  directly call Node APIs without a formal IPC bridge) and were never
  revisited as the application matured and began loading less
  fully-trusted content.
- **The application loads remote web content or user-generated content**
  (an embedded web page, user-supplied HTML) in the same renderer
  configuration as fully trusted application UI, without a security
  boundary between the two.
- **A cross-site scripting (XSS) vulnerability exists in the
  application's own UI code**, and combined with `nodeIntegration`
  enabled, an XSS that would normally be contained to the browser
  sandbox instead grants full Node.js/system access to the attacker.
- **The deprecated `remote` module is used**, providing renderer-side
  access to main-process objects/APIs in a way that similarly expands
  the attack surface if the renderer is ever compromised.

## Diagnose

1. Check the `webPreferences` configuration for every `BrowserWindow`
   created by the application for `nodeIntegration` and
   `contextIsolation` settings, and identify which windows load
   remote/untrusted content versus fully trusted local application UI.
2. Search the codebase for usage of the deprecated `remote` module and
   for direct Node.js API calls from renderer-process code (`require('fs')`
   inside a renderer script, for instance).
3. Assess the application's actual XSS risk surface (any place user
   input or remote content is rendered without proper sanitization) to
   understand the realistic exploitability of the current configuration.
4. Check the Electron version in use and its documented current security
   recommendations, since Electron's own defaults and best practices
   have evolved significantly over time.

## Fix

Enable `contextIsolation: true` and disable `nodeIntegration` for every
renderer, using a properly scoped preload script with
`contextBridge.exposeInMainWorld` to expose only the specific, narrow
set of APIs the renderer actually needs, rather than blanket Node.js
access. Replace any usage of the deprecated `remote` module with
explicit IPC calls (`ipcRenderer.invoke`/`ipcMain.handle`) that the main
process validates and controls. For any window loading remote or
less-trusted content, apply the strictest possible configuration (no
Node integration, no unnecessary IPC exposure, a restrictive Content
Security Policy) and treat it as a genuinely lower-trust boundary
distinct from the application's own trusted UI.

## Pitfalls

Don't expose an overly broad API surface through the preload script's
`contextBridge` as a shortcut to avoid rewriting renderer code that used
to call Node APIs directly -- exposing something like a generic
`runCommand` function defeats the purpose of the isolation boundary just
as much as leaving `nodeIntegration` enabled; expose specific, narrow,
purpose-built functions instead.

## Verify

Confirm `contextIsolation` is enabled and `nodeIntegration` is disabled
across all renderer configurations, and confirm renderer code can only
access the specifically exposed preload-script APIs, not arbitrary
Node.js modules (attempt `require('fs')` from renderer devtools and
confirm it fails). Confirm the application's actual functionality still
works correctly through the new, narrower IPC-based API surface.
