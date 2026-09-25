---
name: lighthouse-pwa-audit-failures
description: Fix specific Lighthouse PWA audit failures methodically, distinguishing checklist-compliance issues from ones that reflect a genuinely broken user experience.
triggers: ["lighthouse pwa score low", "lighthouse pwa audit failing", "installable check failing lighthouse", "pwa checklist fails", "lighthouse pwa category red"]
permissions: ["READ"]
---

## Symptom
Lighthouse's PWA audit category reports one or more failing checks
(installability, service worker registration, offline response, manifest
validity, viewport/theme-color configuration), and it's unclear which
failures reflect a real user-facing problem versus a narrow technical
checklist item.

## Likely causes
1. **Genuine installability gaps** -- manifest issues, no service worker,
   served over HTTP -- covered in depth by `pwa-install-prompt-not-showing`;
   Lighthouse's failures here are a direct, useful signal.
2. **"Page loads while offline" failing** because the service worker
   doesn't have a fetch handler responding to navigation requests at all
   -- directly related to `pwa-offline-fallback-design`.
3. **Theme-color/viewport meta tag checks failing** due to a missing or
   malformed `<meta name="theme-color">` or viewport tag -- a real but
   narrow, easily-fixed issue affecting how the browser chrome/status bar
   renders, not a functional break.
4. **Checks that don't apply well to the app's actual architecture**
   (e.g. an audit expecting a specific caching pattern that doesn't fit a
   highly dynamic, always-online-required application) -- worth
   understanding *why* the check exists before treating every red item as
   equally urgent.

## Diagnose
- Run the Lighthouse PWA audit and read each failing check's own
  explanation and remediation link -- Lighthouse documents what each
  check verifies and why, which is the fastest way to distinguish a real
  UX problem from a narrow technical gap.
- For each failure, ask: does fixing this change what a real user
  experiences, or does it only change what an automated checklist
  reports? Both can be worth fixing, but they don't have the same
  priority.
- Cross-reference failures against the specific other skills in this
  pack (installability, offline experience, caching strategy) for
  failures that indicate a genuinely broken capability, not just a
  missing meta tag.

## Fix
- Prioritize fixes that reflect real user-facing gaps first: a failing
  "responds with 200 when offline" check usually means users genuinely
  get a broken/blank experience offline, which is worth fixing regardless
  of the Lighthouse score itself -- treat the score as a proxy, not the
  goal.
- Fix narrower checklist items (theme-color, viewport meta tags) as
  quick, low-risk wins once the higher-impact issues are addressed --
  they're easy, but shouldn't be prioritized over an actually-broken
  offline experience just because they're faster to clear.
- For an application where a specific check genuinely doesn't fit the
  app's real architecture/use case, document that decision explicitly
  (why it's an intentional gap) rather than either blindly chasing 100%
  or silently ignoring the audit -- future contributors need to know it
  was a deliberate choice, not an oversight.

## Pitfalls
- Optimizing purely for the Lighthouse score number (chasing 100 without
  regard to which checks matter for this specific app) can lead to
  implementing offline caching or install flows the app doesn't actually
  benefit from, adding complexity for a vanity metric.
- Running Lighthouse only in a lab/simulated environment and never
  validating on real devices/networks can miss real-world gaps that the
  simulated audit doesn't fully capture (see `pwa-ios-safari-limitations`
  for one category of platform-specific gap Lighthouse's Chrome-based
  audit won't surface at all).

## Verify
Re-run the Lighthouse PWA audit after fixes and confirm the specific
targeted checks now pass, and separately verify the underlying real user
experience (install flow, offline behavior) manually -- confirming the
score improvement reflects an actual UX improvement, not just a
technicality.
