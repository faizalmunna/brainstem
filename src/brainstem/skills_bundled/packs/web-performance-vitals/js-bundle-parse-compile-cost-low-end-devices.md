---
name: js-bundle-parse-compile-cost-low-end-devices
description: Diagnose a page that loads fast on a fast network but still feels slow to become interactive specifically on low-end or older mobile devices.
triggers: ["slow on low end phones", "fast wifi but page still slow", "high total blocking time", "parse and compile JS slow", "page slow only on old android"]
permissions: ["READ"]
---

## Symptom
Network waterfalls look fine and the page loads quickly on a fast
connection/desktop, but Lighthouse's mobile report (or real users on
budget Android devices) shows a large Total Blocking Time / long "Evaluate
Script" and "Parse HTML" cost, and the page feels sluggish to respond to
input for a second or more after content appears -- this is a CPU-bound
problem, distinct from a bundle simply being large in bytes (that's a
network/transfer problem, see `react-bundle-size-audit` in
frontend-react for that angle).

## Likely causes
1. **JS parse and compile time scales with script size and is highly
   CPU-dependent** -- a bundle that's "not that big" in bytes can still
   take multiple seconds to parse/compile on a low-end device's much
   slower CPU, even though the same bundle parses near-instantly on a
   developer's desktop.
2. **A large amount of code is parsed/compiled even though only a fraction
   executes on this page** (e.g. every route's code bundled together, or a
   large component library imported wholesale), so the device pays the
   parse cost for code it doesn't even run yet.
3. **Polyfills or transpiled-down syntax targeting old browsers are shipped
   to all users**, including modern browsers that don't need them, adding
   dead-weight parse/execution cost universally.
4. **Heavy synchronous initialization code runs on script evaluation**
   (large object construction, regex compilation, eager imports of
   below-fold feature code) rather than being deferred until actually
   needed.

## Diagnose
- Run Lighthouse with mobile CPU throttling (its default mobile preset
  applies ~4x slowdown) and check "Total Blocking Time" and the "Reduce
  JavaScript execution time" audit, which breaks down Parse/Compile/
  Evaluate per script.
- In DevTools > Performance, enable CPU throttling (4x or 6x slowdown) to
  approximate a low-end device even when testing on a fast dev machine,
  then record page load and look at the main thread's "Parse HTML/Script"
  and "Compile Code" entries by duration.
- Compare bundle transfer size (Network panel, "Size" column) against
  actual main-thread script evaluation time (Performance panel) for the
  same script -- a small transfer size with disproportionately large
  evaluation time confirms this is a parse/compile-bound issue, not a
  network issue.
- Check `browserslist`/build target config against actual traffic's
  browser versions (via analytics) to see if legacy transpilation targets
  are broader than the real audience needs.

## Fix
The lever here is reducing how much JavaScript the device's CPU has to
parse and compile at all, not just how many bytes cross the network --
those are different budgets and require different fixes. Concretely:
ship less code per page via route-based code-splitting so a device only
pays parse/compile cost for the code that page actually uses; use
differential serving (`<script type="module">` for modern browsers,
`nomodule` fallback for legacy) so modern-browser users don't pay the
compile cost of transpiled-down, polyfilled code they don't need; defer
initialization of below-fold or non-critical features (lazy-init on
first use, not on script evaluation) so parse and *execution* aren't
both front-loaded; and re-check whether large dependencies pulled in for
minor functionality could be replaced with smaller or native-API
alternatives, since every byte of dependency code still has to be parsed
regardless of how well it's minified.

## Pitfalls
- Minifying/compressing more aggressively reduces transfer size but does
  little for parse/compile time, which is roughly proportional to the
  amount of actual code, not the gzip size -- don't assume a network
  optimization fixes a CPU-bound problem.
- Testing only on a fast development machine or a flagship phone hides
  this class of problem entirely -- always validate with CPU throttling or
  on an actual representative low-end device before declaring it fixed.
- Aggressively code-splitting into many tiny chunks can add enough
  network request overhead (especially on high-latency mobile networks)
  to offset the parse-time savings -- balance chunk count against request
  overhead.

## Verify
Re-run Lighthouse with mobile CPU throttling and confirm Total Blocking
Time and the "Reduce JavaScript execution time" audit both improved, and
if possible test on an actual low/mid-tier Android device (or Chrome
DevTools' device emulation with throttling) to confirm the page responds
to input noticeably faster after load.
