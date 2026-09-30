---
name: storage-tier-mismatch-hot-tier-cold-data
description: Large volumes of infrequently accessed data sit in an expensive, high-performance storage tier because no lifecycle policy moves it to a cheaper tier as it ages.
triggers: ["s3 storage cost too high infrequent access", "cold data stuck in hot storage tier", "storage lifecycle policy missing", "old data never moved to archive tier"]
permissions: ["READ"]
---

## Symptom

A storage cost line item (object storage, block storage snapshots, log
retention) is large and growing, and investigation reveals a significant
fraction of the stored data hasn't been accessed in months, yet it
remains in the same expensive, high-performance storage tier it was
originally written to.

## Likely causes

- **No storage lifecycle policy exists to automatically transition
  objects to a cheaper tier (infrequent-access, archive) based on age or
  last-access time**, so data accumulates indefinitely in whatever tier
  it was originally written to, regardless of whether it's still
  actively used.
- **Data was written to a high-performance tier by default** (the
  simplest/default choice when the storage was first set up) without
  anyone considering tiering at the time, and the default was never
  revisited as data volume grew.
- **Uncertainty about future access patterns discourages tiering** --
  a team is hesitant to move data to a cheaper, higher-latency tier out
  of concern it might be needed again with low retrieval latency, even
  when actual historical access patterns show it essentially never is.
- **Retrieval costs and latency characteristics of colder tiers aren't
  well understood**, leading to an overly cautious default of keeping
  everything in the most expensive, immediately-accessible tier rather
  than matching tier to actual access-pattern requirements.

## Diagnose

1. Analyze actual access patterns (last-accessed timestamps, access
   frequency) for stored data using the storage provider's built-in
   analytics tools (many object storage services provide this natively)
   to identify what fraction of data is genuinely cold.
2. Break down current storage cost by tier and volume to quantify how
   much cost is attributable to data that access-pattern analysis shows
   is rarely or never retrieved.
3. Check whether any lifecycle policy currently exists at all, and if so,
   whether it's actually being applied (some policies are created but
   scoped too narrowly to cover the actual data in question).
4. For specific use cases (compliance-driven long-term retention,
   backups), check the actual retrieval latency/frequency requirements
   against what a colder tier would realistically provide, to confirm
   tiering wouldn't violate a real requirement.

## Fix

Implement lifecycle policies that automatically transition objects to
progressively cheaper tiers based on age and/or observed access
frequency (e.g. move to infrequent-access after 30 days without access,
archive after 90-180 days), using the storage provider's native lifecycle
management features rather than manual, one-off migrations. For new data
being written, choose the appropriate initial tier based on expected
access patterns from the start, rather than defaulting to the most
expensive tier and relying entirely on later lifecycle transitions.
Validate retrieval cost/latency characteristics of colder tiers against
actual real requirements (compliance retrieval SLAs, disaster-recovery
needs) before committing data to them at scale.

## Pitfalls

Don't move data to an archive tier with very high retrieval latency/cost
without confirming it's genuinely rarely needed and that retrieval, if
it does happen, is acceptable under the tier's constraints -- archive
tiers often have retrieval delays measured in hours and per-retrieval
costs that can make a wrong tiering decision expensive to reverse for
data that turns out to still be needed with any regularity. Model
realistic retrieval scenarios before committing large volumes.

## Verify

After implementing lifecycle policies, confirm data is actually
transitioning between tiers as configured (check tier distribution over
time, not just policy existence) and confirm storage cost trends
downward on subsequent billing cycles. Test a retrieval of archived data
in a controlled scenario to confirm the retrieval process and cost/
latency match expectations before relying on it for a real access need.
