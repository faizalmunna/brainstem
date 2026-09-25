---
name: stale-feature-flags-after-full-rollout
description: Feature flags used for a progressive rollout stay in the codebase and config permanently after reaching 100 percent, accumulating as dead complexity.
triggers: ["old feature flags never removed", "feature flag cleanup", "too many stale flags in codebase", "flag still checked after fully rolled out", "technical debt from old feature flags"]
permissions: ["READ"]
---

## Symptom
A feature that was rolled out progressively behind a flag reached 100%
enabled (or was fully decided against) weeks or months ago, but the flag
check, both code branches it guards, and its entry in the flag management
system are all still present -- multiplying over time across many past
rollouts until the codebase has dozens of permanently-on-or-off flags that
nobody is confident are safe to delete, each one a live branch that still
has to be reasoned about and still executes a flag-service lookup on
every request.

## Likely causes
1. **The rollout pipeline/process has a defined path to reach 100% but no
   defined path to actually remove the flag afterward** -- "ship
   progressively" was designed and tooled carefully, but "clean up once
   fully shipped" was left as an implicit, unowned follow-up that
   competes with new feature work for priority and reliably loses.
2. **No tracking of flag age or rollout-completion state** -- the flag
   management system shows current on/off/percentage state but nothing
   surfaces "this flag has been at 100% for 60 days," so there's no
   passive signal that prompts anyone to act; cleanup only happens if
   someone happens to remember.
3. **Removing the flag feels riskier than leaving it**, because the
   person who added it has moved teams, the surrounding code has grown
   organically since, and nobody wants to be the one to delete something
   and find out post-hoc it was silently protecting an edge case --
   leaving it in is the path of least resistance even though it's the
   wrong default.
4. **The flag is entangled with other logic added later**, so removing
   the check isn't a clean deletion anymore -- other conditionals, tests,
   or configuration were written assuming the flag's existence, raising
   the actual (not just perceived) cost of removing it the longer it sits.

## Diagnose
- Query the flag management system for flags that have been at a
  terminal state (100% on, or fully off with the new code path never
  used) for longer than a defined threshold (e.g. 30 days) -- most flag
  platforms expose state-change history/timestamps for exactly this
  query.
- For each candidate flag, grep the codebase for every reference to it
  and check whether any check still branches on it in a way that isn't
  trivially "always true" or "always false" given its current fixed
  state -- if every remaining check is effectively dead code, it's a
  clean removal candidate.
- Check test coverage for both branches of the flag -- if only the
  currently-active branch has real test coverage, the inactive branch is
  already effectively unmaintained and untested dead code, strengthening
  the case for removal rather than "leave it just in case."
- Look for the flag's presence in downstream systems beyond the code
  itself (analytics event properties, logging tags, alerting rules) that
  would also need updating on removal, since these are often what makes
  removal feel riskier than it is when not enumerated explicitly.

## Fix
Treat flag removal as a required, scheduled step of the rollout process,
not an optional follow-up: when a flag is created for a progressive
rollout, create a linked cleanup task at the same time (a ticket, or a
pipeline-enforced expiry) so completing the rollout isn't considered done
until the flag is removed. Add automated staleness detection (a scheduled
job querying the flag platform for flags stuck at a terminal state past a
threshold) that files or nudges a cleanup task automatically rather than
relying on memory. When actually removing a flag, delete both the flag
definition and the now-dead branch it guarded in the same change, run the
remaining code path's test suite to confirm nothing implicitly depended
on the flag-check's side effects (e.g. a cache key or log field derived
from the flag), and remove the flag from the management platform only
after the code deploy referencing it has gone out (never the reverse
order, which would make the flag-service call fail closed against code
that still expects it).

## Pitfalls
- Deleting the flag entry from the management platform before removing
  the code that reads it can cause the flag client to fail or fall back
  to a default in a way that isn't actually equivalent to the intended
  terminal state -- always remove code first, or confirm the client's
  documented fallback behavior matches the intended state exactly.
- Treating "delete the flag" as a pure code-cleanup task assigned with no
  urgency underestimates entanglement risk -- the longer a flag sits
  post-rollout, the more surrounding code tends to grow around both
  branches, so batching many overdue flag removals at once is riskier
  than removing each one shortly after it reaches its terminal state.

## Verify
After removing a flag and its dead branch, confirm the flag no longer
appears in a full-codebase search, run the full test suite for the
affected area to confirm no test still references the flag (a leftover
flag-specific test that now fails or was silently skipped is a sign the
cleanup was incomplete), and confirm the flag no longer appears in the
management platform's active flag list.
