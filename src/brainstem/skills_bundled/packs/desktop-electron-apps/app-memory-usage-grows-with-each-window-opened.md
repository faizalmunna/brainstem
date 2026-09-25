---
name: app-memory-usage-grows-with-each-window-opened
description: An Electron application's total memory usage keeps climbing as users open and close windows over a session, because closed window resources aren't fully released.
triggers: ["electron memory grows opening windows", "closed window memory not released", "electron app memory leak windows", "renderer process not cleaned up"]
permissions: ["READ"]
---

## Symptom

An Electron application's memory usage steadily climbs over the course
of a user session specifically correlated with opening and closing
windows (a settings dialog, a document viewer, a secondary panel) --
memory that should be released when a window closes isn't fully
reclaimed, and repeated open/close cycles accumulate memory usage
indefinitely.

## Likely causes

- **Event listeners registered on the main process for a specific
  window's events aren't removed when that window closes**, keeping a
  reference to the closed window's objects alive through the listener,
  preventing garbage collection of the associated renderer process
  resources.
- **A `BrowserWindow` reference is stored in a data structure (an array,
  a map) but never removed when the window closes**, keeping the
  reference alive on the main-process side even after the actual window
  and its renderer are gone.
- **The renderer process itself has its own memory leak** (event
  listeners, DOM references, closures) that would normally be fully
  reclaimed by the OS when the entire renderer process is terminated on
  window close, but isn't being fully terminated due to a lingering
  reference from the main process.
- **A window is hidden rather than actually closed/destroyed** (a common
  pattern for windows meant to be quickly reopened) but this
  hide-instead-of-close pattern was applied to windows that don't
  actually need to persist, unnecessarily keeping their renderer
  processes and memory alive.

## Diagnose

1. Open and close the same window type repeatedly in a controlled test
   and monitor total application memory (across main and all renderer
   processes) to confirm and quantify the growth pattern.
2. Check the main process code for the specific window type's
   lifecycle -- what happens on its `close`/`closed` event, whether
   listeners are removed and references cleared.
3. Check whether the window is genuinely destroyed (`window.close()`
   leading to actual destruction) or only hidden (`window.hide()`), and
   whether that choice matches the window's actual intended reuse
   pattern.
4. Use Electron's process/memory inspection tools to confirm whether
   renderer processes for closed windows actually terminate, or whether
   they linger as zombie processes still consuming memory.

## Fix

Explicitly remove event listeners registered for a specific window's
lifecycle when that window closes, and clear any stored references to
the closed `BrowserWindow` object from main-process data structures.
Ensure windows meant to be fully closed actually call `close()`/get
destroyed rather than merely hidden, reserving the hide-instead-of-close
pattern specifically for windows with a genuine, deliberate reason to
persist in the background. Verify renderer-side cleanup (removing its
own event listeners, clearing large in-memory data) happens on window
unload for any window type that's frequently opened and closed.

## Pitfalls

Don't apply hide-instead-of-close to every window type as a general
performance optimization to avoid recreation cost -- that trades memory
growth for perceived speed, and should be a deliberate choice only for
windows genuinely expected to be reopened frequently in the same
session, not a default pattern applied everywhere.

## Verify

Repeat the open/close test from the diagnose step after the fix and
confirm memory usage returns to (or very close to) its baseline after
each window closes, rather than accumulating across repeated cycles.
Confirm renderer processes for closed windows actually terminate using
process inspection tools.
