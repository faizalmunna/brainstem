---
name: schema-registry-incompatible-change-breaks-consumers
description: A producer starts sending a new Avro/Protobuf schema version that passes schema registry validation but still breaks existing consumers relying on assumptions the compatibility check didn't cover.
triggers: ["schema registry change broke consumer", "kafka avro schema incompatible", "consumer deserialization error after schema change", "schema evolution broke downstream"]
permissions: ["READ"]
---

## Symptom

A producer team deploys a schema change to a topic, schema registry
compatibility validation passes (no error at publish time), but existing
consumers start failing to deserialize messages, throwing errors, or
silently misinterpreting fields shortly after the new schema version
starts being used.

## Likely causes

- **The schema registry's compatibility mode (backward, forward, full)
  doesn't match what consumers actually need** -- e.g. `BACKWARD`
  compatibility (new schema can read old data) was configured/checked,
  but what was actually needed was `FORWARD` compatibility (old
  consumers can read data written with the new schema), and the specific
  change made was safe for one direction but not the other.
- **A field's semantic meaning changed without a structural schema
  change the compatibility checker would catch** -- e.g. reusing a field
  for a different purpose, or changing units/encoding of a numeric field,
  which passes structural compatibility checks entirely but breaks
  correctness for any consumer that interprets the field the old way.
- **A default value was added for a new field, satisfying structural
  compatibility, but consumers have business logic that doesn't handle
  the default sensibly** (e.g. treating a default `0` as a real value
  rather than "not present"), producing subtly wrong behavior rather than
  an outright deserialization error.
- **Consumers weren't actually validated against the new schema before
  it was published** -- compatibility checking happened only against the
  registry's stored compatibility rules, with no actual test of real
  consumer code against a sample of new-schema messages.

## Diagnose

1. Compare the previous and new schema versions field-by-field, and
   identify exactly what changed -- not just whether the registry
   accepted it, but what compatibility guarantee (backward/forward/full)
   was actually verified.
2. Check the specific consumer's failure mode -- an outright
   deserialization exception points at a structural issue the registry
   should have caught (worth checking why it didn't), while silently
   wrong behavior points at a semantic change the registry structurally
   can't catch.
3. Check the schema registry's configured compatibility mode for the
   topic/subject against what direction of compatibility consumers
   actually depend on (old consumers reading new data, or vice versa).
4. Check whether any consumer-side contract/integration test exists that
   would have caught this before the schema change was published, and
   why it didn't run or wasn't present.

## Fix

Set the schema registry's compatibility mode to match the actual
deployment reality -- if producers and consumers deploy independently
and consumers can't be guaranteed to upgrade before producers, `FULL`
compatibility (both directions) is usually the safer default despite
being more restrictive. For semantic changes that structural
compatibility checking can't catch, establish a process requiring
explicit cross-team review/notification for any schema change, not just
automated registry validation. Add consumer-side contract tests that
actually deserialize and process sample messages using the new schema
before it's published, catching semantic issues that pure structural
compatibility checking misses.

## Pitfalls

Don't relax the schema registry's compatibility mode to make a specific
desired change "pass" without understanding what guarantee is being
given up -- a looser compatibility mode chosen reactively to unblock one
change removes protection for every future change on that topic, not
just the current one. Also don't treat "the registry accepted it" as
sufficient sign-off for a schema change with real semantic implications
-- structural compatibility and semantic compatibility are different
things, and only the former is what the registry actually checks.

## Verify

After tightening compatibility mode and/or adding consumer-side contract
tests, deliberately attempt a schema change of the same class that
caused the original incident and confirm it's now caught before
reaching production (either rejected by the registry, or failed by a
consumer contract test). Confirm existing, legitimate schema evolution
patterns (adding genuinely optional new fields) still work without
being blocked by an overly strict new configuration.
