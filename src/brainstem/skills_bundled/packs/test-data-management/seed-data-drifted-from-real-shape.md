---
name: seed-data-drifted-from-real-shape
description: Tests pass against seed data that no longer reflects what the application actually produces or expects in production, masking bugs that only manifest against real-shaped data.
triggers: ["seed data unrealistic", "tests pass against fake data shape", "seed data does not match production", "test data drifted from reality"]
permissions: ["READ"]
---

## Symptom

A feature works correctly against the test suite's seed data but breaks
in production or staging against real data -- investigation reveals the
seed data represents a data shape (field combinations, value ranges,
relationships) that no longer matches what the application actually
produces or receives from real users, even though it once did.

## Likely causes

- **A business rule changed** (a new required field, a new valid value
  range, a new relationship constraint) and the application code was
  updated to enforce/handle it, but the seed data used in tests was
  never regenerated to reflect the new rule, so tests exercise a data
  shape that no longer represents reality.
- **Seed data was originally hand-crafted once, early in a project**, and
  has simply never been revisited as the domain model evolved over time,
  accumulating drift with every schema/business-rule change since.
- **Seed data represents a narrow, historically convenient scenario**
  (a single simple example customer) that doesn't reflect the diversity
  of shapes real production data has grown to include (optional fields
  that are now usually populated, relationships that are now typically
  many-to-many instead of one-to-one).
- **No process links seed data maintenance to feature/schema changes** --
  updating seed data isn't part of any checklist or review process, so
  it drifts silently unless someone happens to notice.

## Diagnose

1. Compare the seed data's actual field values and relationships against
   a real (anonymized) sample of current production data for the same
   entities, looking specifically for fields that are populated in real
   data but null/default in seed data, or relationship cardinalities that
   differ.
2. For the specific bug that surfaced in production, identify exactly
   what aspect of real data's shape triggered it, and confirm the seed
   data used in tests doesn't include that shape at all.
3. Check whether recent business-rule or schema changes have a
   corresponding seed data update in the same or a nearby commit, or
   whether seed data has been untouched for a notably longer period than
   the schema/business logic around it.
4. Interview the team (or check documentation) for whether seed data
   maintenance is part of any existing process, to understand whether
   this is a one-off gap or systemic to how the team works.

## Fix

Regenerate seed data to reflect the current, real shape of production
data -- ideally by sampling and anonymizing a representative slice of
real (current) data rather than hand-maintaining synthetic data that
tends to drift, or by building seed data programmatically from the same
validation/business-rule code the application itself uses, so seed data
structurally can't violate current rules. Add seed data review as an
explicit step when a business rule or schema change is made, similar to
the fixture-update practice for migrations.

## Pitfalls

Don't regenerate seed data from a single production snapshot and then
let it go stale again with no ongoing process -- this fixes the drift
once but reproduces the same failure mode later unless seed data
maintenance becomes a recurring practice tied to relevant changes, not a
one-time cleanup. Also be careful that sampling real data for seed
purposes still goes through proper anonymization (see this pack's
anonymization skill) -- realistic shape and privacy-safe content are both
required, not a tradeoff between them.

## Verify

Re-run the previously-passing-but-actually-broken tests against the
refreshed seed data and confirm they now fail in a way that reveals the
real bug (or, once the application is fixed, that they pass against
genuinely realistic data). Periodically (e.g. each major schema change)
re-diff seed data shape against a fresh real-data sample to catch future
drift proactively rather than only after a bug surfaces.
