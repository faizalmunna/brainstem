---
name: snapshot-update-masks-real-regression
description: A snapshot test starts failing after a code change, and running the interactive updater makes it pass again without anyone checking whether the new output is actually correct.
triggers: ["snapshot test failing after update snapshots it passes", "jest --ci snapshot mismatch", "should I just update the snapshot", "toMatchSnapshot keeps failing", "vitest -u fixed the test"]
permissions: ["READ"]
---

## Symptom
A `toMatchSnapshot()` test fails after an unrelated (or intentional but
unreviewed) code change. Someone runs `jest -u` / `vitest -u`, the diff
gets accepted wholesale, the test goes green, and the change gets merged
-- but the new snapshot silently encodes a real regression (broken
markup, a missing field, wrong formatting) that nobody actually read
before approving.

## Likely causes
- **The snapshot is treated as a pass/fail gate rather than a diff to
  review** -- the habit of running `-u` the moment a snapshot test fails,
  without ever opening the diff, means the tool can no longer catch
  anything; it just re-records whatever the code currently produces.
- **The snapshot is too large/holistic** (a full component tree, a whole
  API response object) so the diff on any real change is dozens of lines
  of noise, making a genuine one-line regression easy to miss inside it.
- **CI doesn't fail on uncommitted snapshot changes**, so a snapshot
  update made locally to "get the test passing" gets committed alongside
  the regression with no second reviewer ever seeing the `.snap` diff
  called out explicitly in code review.
- **The snapshot was stale before this change** (it already encoded a
  previous, unnoticed regression), so the current diff looks like "adding
  one more field" when it's actually compounding on top of an earlier
  silent break.

## Diagnose
1. Before updating anything, read the actual diff Jest/Vitest prints
   (`--ci` mode will refuse to write and just show it) -- identify
   exactly which fields/lines changed and whether that change was an
   intended effect of the code change being made.
2. Check `git log -p` / `git blame` on the `.snap` file for the section
   in question -- if it was last updated in an unrelated commit with a
   generic message like "fix tests" or "update snapshots", treat the
   existing snapshot as unverified, not as ground truth.
3. Reproduce the underlying behavior manually (render the component, call
   the function, hit the endpoint) outside the snapshot mechanism and
   compare it against what the application is actually supposed to
   produce, not just against the old snapshot.
4. Grep the repo/CI config for `--ci` on the test command -- if snapshot
   tests run without it, any developer's local `-u` can commit an
   unreviewed baseline change with no CI-level friction.

## Fix
Treat every snapshot diff as a code review artifact, not a test flake:
require `--ci` in the CI test command (which fails instead of
auto-writing new snapshots) so updates only ever happen locally and
deliberately, and require the resulting `.snap` diff to be read and
justified in the same PR as the code change that caused it, the same way
a reviewer would read a logic diff. Shrink snapshots to the smallest
meaningful unit (a specific sub-tree, a specific serialized field set)
via targeted `toMatchSnapshot()` calls or property-scoped snapshots
instead of one giant object, so a real regression shows up as an
isolated, readable line rather than buried inside a hundred-line diff.

## Pitfalls
Don't respond to "snapshots are noisy" by deleting snapshot testing
entirely -- for genuinely stable structural output (serialized config,
generated markup for a stable component) it catches real regressions
cheaply; the fix is scoping and review discipline, not abandoning the
tool. Also don't add inline comments instructing reviewers to "just
approve snapshot changes" in PR templates -- that formalizes the exact
rubber-stamping that causes this symptom.

## Verify
Deliberately introduce a real regression (break a formatting rule, drop
a field) in a local branch, run the test suite with `--ci`, and confirm
it fails with a clear diff rather than silently passing -- then confirm
that reverting the regression and re-running still passes without
needing `-u`. This proves the snapshot is still doing its job as a
regression detector, not just a rubber stamp.
