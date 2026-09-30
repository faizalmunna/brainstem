---
name: optional-chaining-swallows-unexpected-nullish-value
description: Optional chaining and nullish coalescing make a genuinely unexpected null or undefined disappear quietly instead of surfacing the bug that produced it.
triggers: ["optional chaining hiding a bug", "why is this silently undefined instead of erroring", "nullish coalescing masking real error", "no error but data missing typescript", "optional chaining everywhere to avoid crashes"]
permissions: ["READ"]
---

## Symptom
A chain like `user?.profile?.settings?.theme ?? 'light'` never throws and
always produces a value, so the UI or logic quietly falls back to a
default even in cases where `user` or `profile` being missing actually
indicates a real bug upstream (a failed fetch, a broken join, an
authorization check that should have redirected instead of rendering).
The team only discovers the underlying problem much later -- a support
ticket, a data audit -- because the optional chain was originally added
to survive one legitimate missing-data case and ended up quietly
absorbing every other case too, expected or not.

## Likely causes
- **Optional chaining was added reactively to fix a crash** (`Cannot read
  properties of undefined`) without first determining whether `undefined`
  at that point was an expected, benign state or a symptom of a real bug
  earlier in the flow -- it silences the crash without distinguishing
  those two very different situations.
- **A nullish-coalescing default is applied at the point of *use* rather
  than at the point of *acquisition***, so every single call site that
  happens to read the value gets its own silent fallback instead of the
  data-fetching layer making one deliberate decision about what a missing
  value means and surfacing it once, loudly, if it's not supposed to
  happen.
- **The optional chain spans a boundary where `undefined` has different
  meanings at each link** -- e.g. `user` being `undefined` legitimately
  means "not logged in yet" (fine to default), but `user.profile` being
  `undefined` for a logged-in user means "profile record failed to load"
  (a real error) -- collapsing both into one `?.` chain treats them
  identically when they shouldn't be.
- **`strictNullChecks` was only turned on recently (or is inconsistently
  applied)**, and the codebase's dominant migration pattern for clearing
  the resulting flood of errors was blanket `?.`/`??` insertion rather
  than case-by-case review of whether each null/undefined was expected --
  a mechanical migration strategy that trades compile errors for silent
  runtime fallbacks en masse.

## Diagnose
1. For a suspect chain, walk it link by link and ask, for each `?.`,
   "under what real condition is this specific link actually
   `null`/`undefined`, and is that condition itself a bug or expected
   state?" -- write this down explicitly per link rather than treating the
   whole chain as one unit.
2. Check whether the same `??` default value shows up in production data
   or logs far more often than the "legitimately missing" case should
   occur (e.g. a `'light'` theme default appearing for 40% of logged-in
   users when the legitimate opt-out rate should be near zero) -- a
   default appearing more than expected is a signal it's absorbing real
   failures.
3. Grep the surrounding data-fetching code for whether errors are already
   being caught and discarded upstream (an empty `catch` block, a
   `.catch(() => undefined)`) that feeds directly into the object being
   optionally chained -- this is often where the "expected" null actually
   originates from a swallowed real error.
4. Temporarily replace one suspect `?.` with a non-optional access in a
   dev/staging environment and see what actually throws -- the resulting
   stack trace usually reveals immediately whether the missing value was
   benign or a symptom of a real upstream failure.

## Fix
Push the null/undefined decision to the point where the data is
acquired, not the point where it's used, and make that decision explicit.
At the data-fetching or object-construction boundary, distinguish
"expected absence" (return a real default or an explicit optional type
with a comment) from "unexpected absence" (throw, log an error, or
surface a typed error result) so that by the time the value reaches
render/use sites deep in the app, its type already reflects a decision
someone made on purpose, rather than every downstream `?.` re-deciding
independently. Where a chain genuinely needs to tolerate a missing link,
keep the `?.`/`??` but add an explicit check (a metric increment, a
`console.warn`, an error-tracking call) at exactly the link where absence
would be surprising, so silent-but-safe absence and silent-but-wrong
absence are no longer indistinguishable in production telemetry.

## Pitfalls
Don't respond to this by removing all optional chaining and replacing it
with non-null assertions (`user!.profile!.settings!.theme`) -- that
swaps a silent wrong-default failure mode for a hard crash on the exact
same unexamined assumption, without actually determining which
null/undefined cases are expected. The fix is deciding, per link, not
picking one blanket operator for the whole codebase. Also avoid adding
telemetry/logging at every single optional-chain link reflexively, which
produces alert fatigue that gets ignored -- reserve it for links where an
absence genuinely indicates a bug, identified via the diagnose step.

## Verify
After distinguishing expected from unexpected absence at the acquisition
boundary, confirm in staging/logs that the "unexpected absence" path
actually fires (a warning, an error log, a typed error) when you
reproduce the real failure condition that originally caused the silent
default, and confirm the "expected absence" path still returns the
correct default without any new noise. Check production error-tracking
over the following days for the new signal to confirm it surfaces at a
rate matching the real underlying failure, not zero (meaning it's still
being swallowed somewhere) and not constantly (meaning the boundary
still doesn't distinguish the two cases correctly).
