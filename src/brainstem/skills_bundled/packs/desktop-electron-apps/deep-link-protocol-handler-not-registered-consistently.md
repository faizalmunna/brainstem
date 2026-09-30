---
name: deep-link-protocol-handler-not-registered-consistently
description: An Electron application's custom URL protocol handler (deep linking) works after a fresh install but stops working after an update, or never registers correctly on one operating system.
triggers: ["electron deep link not working after update", "custom protocol handler broken electron", "deep linking works on install fails later", "electron url scheme not registered"]
permissions: ["READ"]
---

## Symptom

An Electron application registers a custom URL protocol (e.g.
`myapp://`) to support deep linking from a browser or another
application, and it works correctly right after a fresh installation --
but stops working after the application auto-updates, or never worked
correctly on one specific operating system despite working on others.

## Likely causes

- **Protocol registration happens only during the installer's explicit
  registration step, not on every application launch**, so an
  auto-update that replaces the application binary without re-running
  the full installer can leave the OS's protocol registration pointing
  at a stale or now-incorrect path.
- **Different operating systems have fundamentally different mechanisms
  for protocol registration** (Windows registry entries, macOS
  Info.plist declarations, Linux desktop entry files), and the
  application's registration logic only correctly handles one platform's
  mechanism, silently failing on others.
- **Multiple installed versions or installation methods of the same
  application** (a system-wide install and a user-specific install, or
  two different versions) compete for the same protocol registration,
  with the OS resolving to whichever was registered most recently or
  with highest apparent priority, not necessarily the one the user
  expects.
- **The auto-updater replaces the application in a way that changes its
  installation path**, and the OS-level protocol registration still
  points at the old path, causing the protocol handler to fail silently
  or launch a stale binary.

## Diagnose

1. Reproduce the failure specifically after an auto-update (not just a
   fresh install) and check the OS-level protocol registration entry
   (Windows registry key, macOS `LSCopyApplicationURLsForURL`-style
   query, Linux desktop file) for whether it points at a valid, current
   installation path.
2. Check the application's registration logic for whether it re-verifies
   and re-registers protocol handling on every launch, or only during
   an explicit install/first-run step.
3. Check for multiple installations of the application on the affected
   machine that might be competing for the same protocol registration.
4. Compare registration logic across each supported OS to identify any
   platform whose specific registration mechanism isn't correctly
   implemented.

## Fix

Re-verify and, if necessary, re-register the custom protocol handler on
every application launch (not just at install time), so an auto-update
that changes the installation path automatically corrects the OS-level
registration to match. Implement protocol registration correctly and
explicitly for each supported operating system's actual mechanism,
rather than assuming a single cross-platform approach handles all of
them uniformly. Detect and handle the case of multiple installations
gracefully, at minimum logging a clear diagnostic if competing
registrations are detected.

## Pitfalls

Don't register the protocol handler with an absolute path baked in at
build time without re-verifying it at runtime -- installation paths can
vary (user-specific vs. system-wide installs, different install
directories chosen by the user) and a hardcoded assumption will break
for any installation that doesn't match it exactly.

## Verify

Perform a full auto-update cycle in a test environment (install an old
version, trigger an update to a newer version) and confirm the custom
protocol still correctly launches the application afterward, on each
supported operating system. Confirm the protocol handler still resolves
correctly to the current installation path, not a stale one.
