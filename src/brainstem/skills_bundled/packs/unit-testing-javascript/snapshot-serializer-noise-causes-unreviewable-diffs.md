---
name: snapshot-serializer-noise-causes-unreviewable-diffs
description: Every snapshot diff is dominated by irrelevant noise like timestamps, generated ids, or object key ordering, so reviewers stop reading diffs and approve them by habit.
triggers: ["snapshot diff full of noise", "snapshot changes every run for no reason", "generated id breaks snapshot every time", "snapshot key order different", "snapshot diff too big to review"]
permissions: ["READ"]
---

## Symptom
Nearly every `toMatchSnapshot()` diff includes a large amount of
incidental, non-meaningful change -- a different generated UUID, a
`createdAt` timestamp, object keys in a different order, a class instance
serialized with internal fields nobody cares about -- mixed in with (or
completely obscuring) any actual, meaningful change. Reviewers learn that
snapshot diffs are mostly noise and start approving them without reading,
which defeats the purpose described in the companion skill about blindly
updating snapshots.

## Likely causes
- **The object being snapshotted includes non-deterministic fields**
  (a real timestamp, a random ID, a request duration) that were never
  excluded or normalized, so the serialized output legitimately changes
  on every single run regardless of whether the meaningful parts changed.
- **No custom serializer is configured for domain objects that don't
  serialize meaningfully by default** (a Date instance, a Map/Set, a class
  instance with getters), so the default snapshot serializer either dumps
  internal implementation fields or produces inconsistent output across
  environments/library versions.
- **Object/array key order isn't stable across runs or environments**
  (iteration order of a `Map` built from an unordered source, keys
  assembled via `Object.assign` from multiple sources in a
  non-deterministic sequence), so the same logical object serializes
  differently even though nothing about its actual content changed.
- **The snapshot captures a much larger object than the test actually
  cares about** (an entire HTTP response including headers, an entire
  Redux store state) instead of the specific sub-tree relevant to the
  test, so unrelated noise anywhere in that larger object shows up in
  every diff for this test.

## Diagnose
1. Run the same test twice in a row with no code changes in between and
   diff the two snapshot outputs directly -- any difference at all
   between two runs of unchanged code is definitionally noise, not signal,
   and identifies exactly which fields are non-deterministic.
2. Check whether a custom Jest/Vitest snapshot serializer
   (`snapshotSerializers` config, `expect.addSnapshotSerializer`) is
   registered for the object types being snapshotted, or whether the
   default serializer is being relied on for something like a class
   instance or a `Map`.
3. Search recent snapshot-diff PR history (`git log -p -- '**/*.snap'`)
   for a pattern of diffs that only ever touch the same one or two
   fields across many unrelated PRs -- a field that changes in nearly
   every snapshot diff regardless of the actual code change is a strong
   noise candidate.
4. Check what's actually being passed to `toMatchSnapshot()` -- a whole
   response/state object versus a deliberately narrowed sub-object or a
   set of specific properties -- to see whether scope, not just
   non-determinism, is contributing to diff size.

## Fix
Use property matchers for fields that are legitimately non-deterministic
but still worth asserting a *shape* for
(`expect(obj).toMatchSnapshot({ id: expect.any(String), createdAt:
expect.any(String) })`), which locks in the type/presence of the field
without failing on its exact value every run. Register a custom snapshot
serializer for domain types that don't have a meaningful default
serialization (Dates normalized to a fixed format or omitted, class
instances serialized as their meaningful public fields only) so the
output is stable and readable across environments. Normalize non-stable
ordering explicitly before snapshotting (sort object keys, convert a
`Map`/`Set` to a sorted array) rather than relying on incidental iteration
order. Narrow what's actually snapshotted to the specific sub-object or
fields the test cares about instead of an entire large response/state
object, so noise anywhere else in that larger structure can't appear in
this test's diff at all.

## Pitfalls
Don't reach for `expect.any(String)`/property matchers on *every* field
just to make diffs quiet -- over-loosening the matcher on fields that
should actually be asserted precisely (a status code, an error message)
removes real regression coverage, not just noise; apply matchers only to
genuinely non-deterministic fields. Also don't solve noisy ordering by
JSON.stringify-ing the object with a fixed key order purely for the
snapshot without also using that stable form anywhere the real
consumer of the data would see it -- if the normalization only exists to
please the snapshot, a real ordering bug in production could still slip
through unnoticed.

## Verify
Run the affected test five times in a row with zero code changes and
confirm the snapshot produces byte-identical output every time (no diff
at all) -- then make one deliberate, meaningful change to the object's
real content and confirm the resulting diff shows only that change, not
any incidental noise alongside it.
