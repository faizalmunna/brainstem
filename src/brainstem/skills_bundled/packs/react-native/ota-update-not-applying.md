---
name: ota-update-not-applying
description: Fix an over-the-air JS update pushed via CodePush or EAS Update that never takes effect for some users on older native binaries.
triggers: ["codepush update not showing", "eas update not applying", "ota update stuck on old version", "users not getting latest update react native", "expo updates not downloading"]
permissions: ["READ"]
---

## Symptom
A new OTA JS bundle is published (via CodePush or EAS Update), it works
for some users/test devices, but a meaningful segment of users stay stuck
on an older JS version indefinitely -- often correlated with users who
haven't updated the native app binary (App Store/Play Store install) in
a while, even though the OTA push itself reports as successful in the
dashboard.

## Likely causes
1. **Binary/runtime version mismatch gating the update** -- both
   CodePush and EAS Update tie a JS update to a compatible native binary
   version (CodePush's target binary version range, EAS Update's `runtimeVersion`);
   a user on an older native binary than the update's declared
   compatible range will never receive it, by design, because the native
   module/JS API surface may have changed incompatibly.
2. **Update only applied on next cold start, not proactively** -- both
   platforms default to downloading updates in the background and
   applying them on the *next* app launch (or requiring an explicit
   "restart to apply" trigger); a user who keeps the app backgrounded for
   days without a true cold start never sees the new version despite it
   being downloaded and ready.
3. **Rollout percentage/staged deployment not yet at 100%** -- both
   services support gradual rollout; users outside the current rollout
   percentage correctly haven't received the update yet, which can look
   identical to "OTA is broken" if the rollout config isn't checked.
4. **A channel/deployment key mismatch** -- the app build was compiled
   pointing at a different deployment key/channel (e.g. a "Staging" key
   left in a production build, or an EAS Update channel not matching the
   build profile's configured channel), so it's polling for updates in
   the wrong place entirely.
5. **The update check itself failing silently** -- a network error, a
   misconfigured update server URL, or an exception in the update-check
   call being swallowed without surfacing anywhere, so the app never
   even learns an update exists.

## Diagnose
- Check the specific user's/device's reported native binary version
  against the update's configured minimum/target binary version
  (CodePush) or `runtimeVersion` (EAS Update) -- a mismatch here is
  "working as intended," not a bug, and the real fix is a native
  binary release, not a re-push of the OTA update.
- Check the rollout percentage on the specific deployment/branch in the
  CodePush or EAS dashboard -- confirm it's actually at 100% if universal
  rollout was intended.
- Log (or check via the dashboard's device-level diagnostics, where
  available) which deployment key/channel the affected build is actually
  polling -- compare the key/channel baked into the build against the one
  the update was published to.
- Add explicit logging/error handling around the update-check and
  download calls (`codePush.sync()`'s status callback, or
  `Updates.checkForUpdateAsync()`/`fetchUpdateAsync()`'s result and
  thrown errors) rather than trusting a bare fire-and-forget call, so a
  silent failure becomes visible in logs/crash reporting.
- Reproduce cold-start application behavior directly: after confirming a
  download succeeded, fully force-quit the app and relaunch, and confirm
  the update applies then -- if it doesn't even apply on a true cold
  start, the issue is deeper than "user hasn't restarted."

## Fix
- Treat binary-version incompatibility as a signal to ship a native
  binary update, not to chase the OTA path further -- OTA updates are for
  JS/asset changes compatible with the currently-installed native code,
  not a replacement for App Store/Play Store releases when native
  code/dependencies changed.
- If waiting for the next cold start is too slow for the use case, use
  the platform's explicit "apply immediately" option deliberately
  (CodePush's `InstallMode.IMMEDIATE`, or EAS Update's
  `Updates.reloadAsync()` after confirming a fetched update) with a clear
  user-facing prompt, since force-restarting a user's app without warning
  is jarring.
- Correct the rollout percentage or explicitly promote the release to
  100% once validated, rather than assuming a partial rollout was a full
  one.
- Fix the deployment key/channel configuration at the build-profile
  level (`android`/`ios` native config for CodePush keys, or
  `eas.json`'s channel mapping for EAS Update) and ship a corrected
  native build if the wrong key/channel was baked into an already-
  released binary -- an OTA fix cannot correct a wrong deployment key
  baked into the binary, since that's the very thing controlling where it
  looks for updates.
- Add monitoring/alerting on the update-check failure path so silent
  network/config failures surface instead of only being noticed when a
  user reports being stuck on an old version.

## Pitfalls
- Re-publishing the same OTA update repeatedly when the real issue is a
  binary-version mismatch wastes rollout cycles and doesn't reach the
  affected users no matter how many times it's pushed -- confirm binary
  compatibility before assuming the publish itself is broken.
- Force-applying updates immediately on every launch without checking
  install mode implications can interrupt a user mid-task (losing unsaved
  form input, e.g.) when the app suddenly reloads -- reserve immediate
  install for critical fixes and prefer "apply on next restart" for
  routine updates.

## Verify
On a device pinned to the affected binary version and deployment
key/channel, confirm the update check reports the new version as
available, the download completes, and the update is actually running
(check a version indicator baked into the update, e.g. a visible build
number) after either the configured install trigger or a full app
restart -- and confirm this for a device at the edge of the rollout
percentage boundary, not only a fully-rolled-out one.
