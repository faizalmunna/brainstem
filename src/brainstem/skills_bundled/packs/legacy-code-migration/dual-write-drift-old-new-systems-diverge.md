---
name: dual-write-drift-old-new-systems-diverge
description: A migration's dual-write period (writing to both the old and new systems simultaneously) allows the two to silently drift out of sync because no reconciliation or consistency check was built in.
triggers: ["dual write systems out of sync", "old and new system data diverged", "migration drift no reconciliation", "dual write period data mismatch"]
permissions: ["READ"]
---

## Symptom

During a migration's transition period, where the application writes to
both the old and new systems to keep them in sync before fully cutting
over, the two systems are discovered to have diverged -- data present in
one but not the other, or with different values -- and there was no
mechanism in place to detect this before it accumulated into a larger
reconciliation problem.

## Likely causes

- **A write to one system succeeded while the corresponding write to the
  other failed**, and the dual-write logic didn't handle partial failure
  explicitly (no retry, no alert, no compensating action), so the
  failure was silent and the two systems immediately began diverging
  from that point.
- **The dual-write logic itself has a bug** (a field mapping error, an
  off-by-one in a transformation) that produces subtly different data in
  the new system compared to the old one, even when both writes
  "succeed," so the drift isn't a failure at all but a silent
  correctness bug in the migration code.
- **No automated reconciliation/consistency check was built to compare
  the two systems periodically**, so drift accumulates invisibly until
  someone happens to notice a specific discrepancy manually, by which
  point a potentially large amount of undetected drift has built up.
- **A direct write path to one of the systems bypasses the dual-write
  logic entirely** (an admin tool, a data-fix script, a different code
  path added after the dual-write was set up) without anyone updating it
  to also write to the other system.

## Diagnose

1. Build (if it doesn't exist) or run an existing reconciliation check
   comparing a sample or the full dataset between old and new systems to
   quantify the actual current extent of drift.
2. For specific discrepancies found, trace back to when the divergence
   began (via timestamps, audit logs) to narrow down whether it's an
   ongoing bug or a one-time failure event.
3. Review the dual-write implementation for how it handles partial
   failure -- does a failure on one side roll back, retry, alert, or
   silently proceed as if it succeeded?
4. Audit all code paths that write to either system for whether they all
   correctly go through the dual-write logic, or whether any bypass path
   exists.

## Fix

Fix any identified dual-write bugs (mapping errors, partial-failure
handling) so both systems reliably receive correct data going forward,
including explicit handling for partial failure -- either both writes
succeed, or the operation is retried/alerted/compensated, never silently
"succeeds" with only one side actually written. Build an automated,
regularly-run reconciliation job that compares the two systems and
alerts on drift beyond an acceptable threshold, so future divergence is
caught quickly rather than discovered much later. For already-accumulated
drift, run a one-time reconciliation to bring the systems back in sync,
treating the new system (the migration target) as authoritative unless
specific evidence suggests otherwise for particular records.

## Pitfalls

Don't treat the reconciliation job as a one-time cleanup rather than an
ongoing safeguard -- drift can recur from a new bug or a new bypass path
introduced later, so reconciliation needs to run continuously (or
regularly) throughout the entire dual-write period, not just once when
drift is first discovered. Also don't silently auto-fix every detected
discrepancy without understanding its cause -- some discrepancies might
indicate a bug worth fixing at the source rather than just papering over
with a reconciliation patch each time.

## Verify

Run the reconciliation check regularly after the fix and confirm drift
stays at zero (or within an acceptable, explained threshold) going
forward. Before final cutover away from the old system, run a final,
comprehensive reconciliation to confirm full consistency, not just a
sampled check.
