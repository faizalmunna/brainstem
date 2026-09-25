---
name: navigation-state-reset-on-backgrounding
description: Fix navigation stacks that reset to the initial screen after the app is backgrounded and then reopened by the user.
triggers: ["navigation resets when app backgrounded", "app goes back to home screen after switching apps", "navigation state lost after backgrounding", "screen resets on app resume", "react navigation state gone after minimizing"]
permissions: ["READ"]
---

## Symptom
A user navigates several screens deep, switches to another app or lets
the device lock, then returns to find the app back on the initial/home
screen instead of where they left off -- sometimes only on Android,
sometimes only after the OS has been under memory pressure, sometimes
every single time.

## Likely causes
1. **Android process death, not an app bug at all** -- Android can kill a
   backgrounded app's process to reclaim memory, and on relaunch the
   *activity* is recreated fresh; without persisted navigation state, the
   navigator legitimately has nothing to restore and falls back to its
   initial route.
2. **Navigation state persistence not wired up** -- React Navigation
   supports persisting/restoring `NavigationContainer` state
   (`onStateChange` + `initialState` from storage), and if that isn't
   implemented, every fresh mount (including ones caused by process
   death) starts from the configured initial route by design, not by bug.
3. **The root navigator's `key` or the app's root component being
   remounted on resume** -- an `AppState` listener or a top-level
   conditional (e.g. re-checking auth on foreground) that swaps out the
   `NavigationContainer`'s subtree or changes a `key` prop, forcing React
   to tear down and recreate the whole navigation tree.
4. **Deep-link or push-notification handling on resume overwriting the
   current route** -- a `Linking` listener or notification-tap handler
   that unconditionally calls `navigation.reset()`/`navigate('Home')`
   whenever the app comes to the foreground, regardless of whether that
   foreground event was actually caused by a link.
5. **Redux/Context state driving conditional screens getting reset** --
   if which stack renders (e.g. auth vs. main) depends on state that gets
   reinitialized (a store rehydration race, a context provider
   remounting with default values) before persisted data loads back in.

## Diagnose
- Reproduce deliberately: on Android, enable Developer Options > "Don't
  keep activities" -- this forces process death on every background,
  turning an intermittent bug into a 100%-reproducible one and confirming
  whether it's specifically a cold-restart-after-death issue.
- Add a log line in the root component's mount and in any `AppState`
  change listener (`AppState.addEventListener('change', ...)`) to see
  whether the whole tree remounts on resume vs. just an `AppState` event
  firing.
- Check whether `NavigationContainer` has `onStateChange` wired to
  persistence and `initialState` wired to restoration -- if neither
  exists, state loss on process death is expected behavior, not a bug to
  chase further upstream.
- Search for `navigation.reset(` and `navigation.navigate('Home'` calls
  gated on `AppState` or `Linking` events, and check whether they're
  conditioned on an actual deep link/notification payload being present.

## Fix
- Implement React Navigation's state persistence: save
  `NavigationContainer`'s state via `onStateChange` (debounced, to
  `AsyncStorage` or similar) and pass it back in as `initialState` on
  mount (guarded by an "app has fully loaded persisted state" check so
  you don't briefly flash the default route before restoration
  completes).
- Scope any `AppState`-triggered navigation logic (deep link resume,
  auth re-check) so it only fires navigation actions when there's an
  actual reason to (a pending link URL, an expired token), not on every
  foreground transition -- foregrounding by itself should never imply
  "go to home."
- Avoid changing a `key` prop on `NavigationContainer` or its ancestors
  based on transient state; if the app needs to swap between an
  authenticated and unauthenticated navigator, do it by conditionally
  rendering inside a *stable* container structure, not by remounting the
  container itself.
- If the "reset" is actually correct product behavior for security
  reasons (e.g. re-auth after backgrounding for a banking app), make it
  explicit and intentional (a timeout-based re-auth screen) rather than
  an accidental side effect of remounting.

## Pitfalls
- Persisting navigation state without versioning it breaks on the next
  app update if the navigator structure changes (a renamed/removed
  screen referenced in old saved state) -- guard restoration with a
  version check and fall back to a fresh state on mismatch rather than
  crashing on an invalid route name.
- Restoring navigation state but not the data that screen depends on (a
  detail screen that expects an item already loaded into memory/Redux)
  can restore the *route* successfully while rendering a broken screen --
  test restoration after a real process kill, not just a JS-level reload.

## Verify
With "Don't keep activities" enabled (Android) or after force-quitting
the app via the OS app switcher, navigate several screens deep, background
the app, kill it via the developer setting, then reopen from the app
icon and confirm the app returns to the same screen (or an intentional,
explicit fallback) with correct data, not the initial route.
