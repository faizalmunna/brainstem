---
name: ipc-message-handler-blocks-main-process
description: An Electron application's UI freezes across all windows because a synchronous IPC handler in the main process performs slow, blocking work.
triggers: ["electron app freezes on ipc call", "main process blocked electron", "electron ui frozen synchronous ipc", "electron app unresponsive during operation"]
permissions: ["READ"]
---

## Symptom

An Electron application's entire user interface (potentially across
multiple windows) becomes unresponsive during a specific operation --
menus don't open, windows don't redraw, other windows besides the one
that triggered the operation also freeze -- traced to an IPC (inter-
process communication) handler registered in the main process that
performs slow, synchronous work.

## Likely causes

- **A synchronous IPC handler (`ipcMain.on` combined with a
  `sendSync`-style call, or any handler doing blocking work)** performs
  file I/O, a CPU-intensive computation, or a network call directly on
  the main process's single event loop thread, and Electron's main
  process architecture means blocking it freezes every window's ability
  to receive main-process-mediated events.
- **A native Node.js module called from the main process performs
  synchronous, blocking I/O** (a sync file read, a sync subprocess call)
  when an asynchronous equivalent was available but not used.
- **Heavy computation was placed in the main process out of convenience**
  (easier access to Node APIs) without considering that the main process
  is uniquely single-threaded and shared across the entire application's
  UI responsiveness, unlike a renderer process which only affects its
  own window.
- **A long-running operation has no progress reporting or chunking**, so
  even if it's technically asynchronous, it monopolizes the event loop
  for extended periods between yield points.

## Diagnose

1. Identify the specific IPC channel/handler responsible by correlating
   the freeze timing with a specific user action, then inspecting that
   handler's implementation in the main process code.
2. Check whether the handler performs any synchronous I/O or CPU-bound
   work directly, and whether asynchronous equivalents exist for the
   specific operations used.
3. Profile the main process (Electron/Node.js support standard V8
   profiling tools) during the freeze to confirm the main process's
   event loop is genuinely blocked, not merely a rendering issue in one
   window.
4. Check whether the operation could instead be delegated to a
   worker thread, a child process, or performed in the renderer process
   instead of main, if it doesn't specifically require main-process-only
   APIs.

## Fix

Replace synchronous I/O calls in main-process IPC handlers with their
asynchronous equivalents, and use `ipcMain.handle`/`ipcRenderer.invoke`
(the modern async-first IPC pattern) rather than synchronous
`sendSync`-style APIs for anything beyond trivial, fast operations. For
genuinely CPU-intensive work, move it to a Node.js worker thread or a
separate child process rather than running it directly on the main
process's event loop, communicating results back via IPC once complete.
For long operations, report progress incrementally rather than blocking
until full completion, keeping the main process responsive throughout.

## Pitfalls

Don't move blocking work to the renderer process as a blanket fix
without considering that this can still freeze that specific window's
UI (though not the whole app) -- for genuinely CPU-intensive work, a
worker thread or child process is the more robust fix regardless of
which process it was originally blocking.

## Verify

Reproduce the original triggering action after the fix and confirm the
application (including other windows, and the main process's own
responsiveness like the system tray or global shortcuts) remains fully
responsive throughout the operation. Profile the main process during the
same operation and confirm the event loop is no longer blocked for an
extended period.
