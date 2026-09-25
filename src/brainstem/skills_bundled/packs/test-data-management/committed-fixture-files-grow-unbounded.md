---
name: committed-fixture-files-grow-unbounded
description: Large snapshot or fixture files committed to the repository grow steadily over time, slowing down checkout and CI without anyone noticing the accumulating cause.
triggers: ["repo checkout getting slow", "fixture files huge", "snapshot files bloating repo", "ci checkout time increasing gradually"]
permissions: ["READ"]
---

## Symptom

Repository checkout, CI job startup, or general git operations (clone,
fetch, diff) have gradually gotten noticeably slower over months, and
nobody has an obvious single cause -- eventually traced to a steadily
growing set of committed fixture or snapshot files (large JSON payloads,
binary test data, generated snapshot output) rather than to source code
growth.

## Likely causes

- **Every new test that needs example data adds its own new fixture
  file** rather than reusing or trimming existing ones, so fixture data
  volume grows roughly proportional to test count with no natural upper
  bound.
- **Snapshot testing (UI component snapshots, API response snapshots)
  accumulates large text/binary blobs per test**, and outdated snapshots
  for removed or renamed tests are never cleaned up, only ever added to.
- **Fixture files capture far more data than a given test actually
  needs** (a full realistic API response with dozens of fields when a
  test only asserts on two of them), inflating each individual file's
  size well beyond what's necessary.
- **Binary or generated fixture files are committed directly to git**
  rather than being generated on demand or stored via a mechanism better
  suited to large binary blobs (Git LFS, an external fixture store),
  so git's history retains every version of every large file forever.

## Diagnose

1. Run a repository size analysis (tools that show the largest files/
   directories in git history, not just the current working tree) to
   identify whether fixture/snapshot files are actually the dominant
   contributor to repo size and checkout time.
2. Check whether fixture/snapshot file count and total size have grown
   roughly in proportion to test count, or disproportionately (a sign of
   individual files getting larger, not just more numerous).
3. Look for orphaned snapshot/fixture files with no corresponding active
   test referencing them (removed or renamed tests whose fixtures were
   never cleaned up).
4. Sample a few large fixture files and check how much of their content
   is actually used/asserted on by the corresponding test versus unused
   padding.

## Fix

Trim fixture files to include only the fields/data a test actually
needs, rather than a full realistic payload captured wholesale. Add a
periodic (or CI-enforced) check for orphaned snapshot/fixture files with
no referencing test, and remove them. For large binary or
frequently-regenerated fixture data, consider Git LFS or generating
fixtures on demand (from a smaller canonical source or a factory) rather
than committing every large variant directly into normal git history.
For snapshot testing specifically, review and prune stale snapshots as a
routine part of the snapshot-update workflow, not just when someone
happens to notice repo bloat.

## Pitfalls

Don't attempt to rewrite git history to remove already-committed large
files as a first response without understanding the disruption this
causes to every existing clone/fork/branch -- weigh that cost explicitly
against the ongoing cost of the bloat, and prefer preventing further
growth first; a history rewrite (if pursued) is a separate, carefully
planned, and communicated operation, not a quick fix.

## Verify

Measure repository clone/checkout time and total size before and after
trimming/removing genuinely orphaned or oversized fixtures, and confirm a
measurable improvement. Set up an ongoing check (part of CI or a
periodic script) that flags newly added large fixture files or growing
snapshot directories going forward, so the same accumulation doesn't
silently recur.
