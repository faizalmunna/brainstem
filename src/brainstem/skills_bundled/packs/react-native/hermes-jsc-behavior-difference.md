---
name: hermes-jsc-behavior-difference
description: Debug subtle JavaScript behavior differences that only appear when running on the Hermes engine instead of JSC.
triggers: ["works with jsc but not hermes", "hermes different behavior", "bug only happens with hermes enabled", "hermes engine bug react native", "intl not working hermes"]
permissions: ["READ"]
---

## Symptom
Code that behaves correctly under JSC (or in a Node/browser environment
during testing) produces different output, throws, or silently misbehaves
specifically when running on Hermes -- common flavors: date formatting or
`Intl` output differs, a regex behaves differently, error stack traces
look unrecognizable, a library that "definitely works" upstream fails in
a way that only reproduces with Hermes enabled.

## Likely causes
1. **A library written assuming full `Intl` support**, which older
   Hermes versions shipped only partially (or required an explicit
   opt-in build flag for) -- `Intl.NumberFormat`/`DateTimeFormat` calls
   that work under JSC silently fall back to different formatting, wrong
   locale data, or throw under Hermes if the needed `Intl` API isn't
   present in the Hermes build being used.
2. **Reliance on JS engine implementation details the spec doesn't
   guarantee** -- object key iteration order edge cases, specific
   `Error.stack` string formatting, or timing quirks (`setTimeout(fn, 0)`
   ordering relative to microtasks) that happened to match JSC's behavior
   by coincidence and a test or library encoded that coincidence as an
   assumption.
3. **Hermes's stricter/different handling of certain syntax or bytecode
   precompilation** -- Hermes precompiles to bytecode ahead of time,
   which can surface issues with dynamically-`eval`'d code or certain
   proposal-stage syntax that JSC's JIT tolerated differently.
4. **A pinned Hermes version lagging the RN version's expectations** --
   Hermes is versioned somewhat independently and bundled per RN release;
   a library assuming a newer Hermes feature (a specific `Intl` API, a
   newer TC39 feature) can fail on an older bundled Hermes even on a
   supported RN version.
5. **Third-party polyfills conflicting with Hermes's own partial native
   implementation of a feature** -- a polyfill that checks
   `typeof Intl.PluralRules === 'undefined'` to decide whether to
   polyfill can get it wrong if Hermes provides a partial/stubbed version
   that passes the `typeof` check but behaves incompletely.

## Diagnose
- Confirm the engine actually in use: log `global.HermesInternal != null`
  or check `global._HERMES_VERSION_` -- don't assume from RN version
  alone, since Hermes can be explicitly disabled per-platform in
  `android/app/build.gradle` (`hermesEnabled`) or the iOS Podfile.
- Reproduce the exact failing snippet in isolation in the Hermes REPL
  (`node_modules/react-native/sdks/hermesc/<platform>/bin/hermes` or via
  a minimal RN debug build) versus a plain Node REPL, to confirm the
  divergence is engine-specific and not something else entirely (a
  timing bug, a data issue).
- Check the installed Hermes version against the library's minimum
  supported version/known-issues list -- many libraries document Hermes
  version caveats explicitly in their README or issue tracker.
- For `Intl`-related bugs specifically, log
  `Intl.NumberFormat('en-US').resolvedOptions()` (or the relevant `Intl`
  constructor) and compare the resolved options/output between the JSC
  and Hermes builds side by side.

## Fix
- Enable full `Intl` support in Hermes if the RN/Hermes version requires
  an explicit flag (older RN versions needed `hermesEnabled` plus a
  separate Intl polyfill or build config; check current RN docs for the
  version in use, since this has changed across RN releases as Hermes's
  `Intl` support matured).
- Replace assumptions about implementation-defined behavior with
  spec-guaranteed behavior -- e.g. don't rely on `Object.keys()` order
  for anything other than the guaranteed insertion-order-for-string-keys
  spec behavior, and don't parse `Error.stack` format strings since
  they're non-standardized and differ by engine and by minification.
- Pin/upgrade to a library version with confirmed Hermes compatibility,
  or add a Hermes-specific code path only where the underlying capability
  genuinely differs, rather than patching around symptoms.
- If a polyfill's feature-detection is fooled by Hermes's partial native
  implementation, force the polyfill explicitly (bypass the `typeof`
  check) rather than relying on the library's own detection logic.

## Pitfalls
- "Just disable Hermes" is not a durable fix -- Hermes is the default
  engine for new RN apps and JSC support is being phased down over time
  in the ecosystem, so avoiding Hermes trades today's bug for a worse one
  later when JSC-specific paths become unsupported or unmaintained.
- Assuming any Hermes-vs-JSC difference is a Hermes bug rather than the
  app's own code relying on non-spec behavior leads to filing/waiting on
  upstream issues that never get "fixed" because Hermes's behavior may
  actually be the spec-correct one and JSC's was the outlier.

## Verify
Run the specific failing code path on a Hermes-enabled build and confirm
correct output/behavior, then re-run the app's broader test suite (or a
manual smoke test of features depending on the same API, e.g. all
locale-formatted dates/numbers in the app) with Hermes enabled to catch
any other spots relying on the same incorrect assumption.
