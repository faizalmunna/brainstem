---
name: metro-bundler-stale-cache
description: Fix Metro serving an old JS bundle so code changes don't appear in the running app despite editing and saving source files.
triggers: ["metro cache stale code", "changes not showing up react native", "metro bundler not updating", "fast refresh not working", "old code still running after edit"]
permissions: ["READ"]
---

## Symptom
Source files are edited and saved, Fast Refresh appears to trigger (or a
manual reload is done), but the app keeps running old logic -- a
console.log that was removed still prints, a fixed bug still reproduces,
or a renamed variable still throws the old error, even after multiple
reloads.

## Likely causes
1. **Metro's on-disk transform cache serving a stale transformed module**
   -- Metro caches transformed file output keyed by file content hash and
   dependencies; a cache invalidation bug (common after switching git
   branches with large diffs, or after a Babel/Metro config change that
   isn't part of the cache key) can serve an old transform for a file
   whose source hash Metro fails to recognize as changed.
2. **A stale pre-bundled JS file being loaded instead of Metro's live
   bundle** -- release-mode builds, or a debug build that was previously
   run with `bundleInDebug`/an embedded bundle, can load a bundled
   `.jsbundle`/`index.android.bundle` file that was generated once and
   never regenerated, so no amount of Metro-side changes matter because
   Metro isn't even being hit.
3. **Multiple Metro instances running** -- an old `metro`/`react-native
   start` process left running in another terminal (or a stale process
   after a crash) still serving requests on the same port, while a newer
   instance was started elsewhere; the app happens to be connected to the
   stale one.
4. **watchman not picking up file system events** -- on some setups
   (network drives, certain Docker/WSL configurations, or after watchman
   itself crashes silently), file changes stop being detected, so Metro
   never even attempts to re-transform the changed file.
5. **A `.babelrc`/`babel.config.js`/`metro.config.js` change that isn't
   itself part of what Metro watches for invalidation**, so changing how
   files are transformed doesn't invalidate already-cached transforms of
   unrelated files.

## Diagnose
- Check how many Metro processes are actually running: `lsof -i :8081`
  (or the configured port) on macOS/Linux, or check Task Manager /
  `netstat -ano | findstr 8081` on Windows, and kill any but the intended
  one.
- Confirm the app is loading from Metro at all, not an embedded bundle --
  check the dev menu for "Reload" being present/functional (an embedded-
  bundle release build typically has this disabled or absent) and check
  build settings for `bundleInDebug`/`forceBundling` flags.
- Add a deliberately obvious change (e.g. a giant emoji in a visible
  string) and reload -- if it doesn't appear, the problem is bundle
  delivery, not a subtler logic bug being mistaken for a cache issue.
- Check watchman's health: `watchman watch-list` to confirm the project
  directory is watched, and `watchman watch-del-all` as a diagnostic
  reset if file events seem to not be firing.

## Fix
- Clear Metro's cache explicitly rather than guessing: `react-native
  start --reset-cache` (or `expo start -c`), which clears Metro's
  transform cache directory. If that doesn't resolve it, also clear
  `$TMPDIR/metro-*` and `$TMPDIR/haste-map-*` manually, since some cache
  artifacts live outside the reset-cache path in older Metro versions.
- Kill every running Metro process for the project before starting a
  fresh one, to eliminate the "stale second instance" cause entirely
  rather than assuming there's only one.
- If an embedded/pre-bundled JS file is the actual source, delete it
  (`ios/main.jsbundle`, `android/app/src/main/assets/index.android.bundle`)
  and rebuild so the app is forced back onto Metro's live bundle for
  development, or regenerate the bundle deliberately when release-style
  testing is actually intended.
- Reset watchman (`watchman watch-del-all` then restart Metro) when file
  changes aren't triggering any rebuild activity at all (no log output in
  the Metro terminal on save).

## Pitfalls
- Reflexively running `rm -rf node_modules && npm install` as the first
  response to "stale code" is a much bigger hammer than the actual fix
  in most cases and doesn't address stale embedded bundles or duplicate
  Metro processes at all -- diagnose which of the causes above actually
  applies before reaching for a full dependency reinstall.
- Clearing Metro's cache repeatedly without ever checking for a second
  running instance or an embedded bundle just resets the wrong cache
  layer each time, producing a "sometimes it works after a few tries"
  impression that's actually random luck about which Metro instance
  handled the last request.

## Verify
Make an unambiguous, visible source change (a distinct log message or UI
text), reload the app once, and confirm the exact new content appears --
then repeat the whole edit-reload cycle two or three more times in a row
to confirm the fix isn't just a one-time cache clear masking an
underlying process/config issue that will recur.
