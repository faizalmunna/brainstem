---
name: topic-deletion-permanent-data-loss-no-recovery
description: A Kafka topic is accidentally deleted (or recreated with the same name) through an automated cleanup script or a mistaken manual command, permanently losing its data with no built-in recovery path.
triggers: ["kafka topic accidentally deleted", "topic deletion no backup", "automated cleanup deleted wrong kafka topic", "kafka data permanently lost topic delete"]
permissions: ["READ"]
---

## Symptom

A Kafka topic that was actively in use suddenly has no data, or consumer
applications start failing with errors indicating the topic doesn't
exist (or has a different partition count/configuration than expected)
-- traced back to a topic deletion, either from an automated cleanup
script matching an unintended pattern, or a manual command run against
the wrong environment/topic.

## Likely causes

- **An automated cleanup script targeting genuinely unused/temporary
  topics matched a topic name pattern too broadly**, catching an
  actively-used topic that happened to share a naming convention with
  topics that were actually meant to be cleaned up.
- **A manual `kafka-topics --delete` command was run against the wrong
  cluster/environment** (production instead of staging) due to a
  misconfigured CLI context or an operator error under time pressure.
- **A topic was deleted and recreated with the same name as part of a
  configuration change** (changing partition count, which requires
  recreation in older Kafka setups) without realizing recreation resets
  the topic completely, losing all existing data rather than preserving
  it.
- **No confirmation step or dry-run capability was used before a
  destructive topic operation**, and no backup/replication to a separate
  system existed as a safety net for this specific topic's data.

## Diagnose

1. Confirm the deletion actually occurred (check Kafka's own logs for a
   `DeleteTopic` administrative event, and check any automation/CI logs
   for a script run around the time data disappeared) rather than
   assuming based on symptoms alone.
2. If a script is suspected, review its exact matching logic against the
   actual topic name that was deleted, to confirm and understand the
   specific pattern-matching gap.
3. Check whether Kafka's own topic deletion has any grace period or
   soft-delete behavior in the specific version/configuration in use
   (most Kafka deployments delete topics immediately and permanently, but
   confirm rather than assume).
4. Check whether any downstream sink (a connector writing to object
   storage, a separate long-term archive) independently retained a copy
   of the topic's data before deletion.

## Fix

For any topic where deletion would be unacceptable, use Kafka's topic-
level deletion protection settings if the distribution/version supports
them, or restrict `DeleteTopic` ACL permissions to a small, deliberate
set of operators/service accounts rather than broad administrative
access. Fix automated cleanup script matching logic to be maximally
specific (exact names or narrowly scoped patterns with an explicit
allowlist) rather than broad pattern matching that could catch
unintended topics, and add a dry-run/confirmation step before actual
deletion for any automated cleanup. For genuinely critical topics,
maintain an independent durable copy (a sink connector to object storage,
or cross-cluster replication) so accidental topic deletion doesn't mean
unrecoverable data loss.

## Pitfalls

Don't restrict deletion permissions so broadly that legitimate,
necessary cleanup of genuinely temporary topics becomes an operational
burden requiring excessive approval overhead -- scope protection to
topics that actually need it (identified by naming convention or
explicit tagging) rather than blanket-restricting all topic deletion
across the entire cluster.

## Verify

After implementing protection measures, attempt a deliberate test
deletion of a protected topic in a non-production environment and
confirm it's correctly blocked or requires the intended additional
confirmation step. For topics with independent durable copies, verify
the archival mechanism actually captures current data by testing a
restore from the archive against a specific known message.
