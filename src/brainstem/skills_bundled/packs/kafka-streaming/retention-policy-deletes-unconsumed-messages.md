---
name: retention-policy-deletes-unconsumed-messages
description: A slow or delayed consumer permanently loses messages because Kafka's topic retention policy deleted them before the consumer caught up to read them.
triggers: ["kafka messages deleted before consumed", "consumer permanently behind retention", "kafka retention period too short", "lost messages from topic retention expiry"]
permissions: ["READ"]
---

## Symptom

A consumer that fell significantly behind (due to an extended outage, a
slow reprocessing run, or a paused consumer) comes back online and finds
a gap in the message sequence it expected to process -- some messages it
needed are simply gone, deleted by Kafka's topic retention policy before
the consumer ever reached them.

## Likely causes

- **The topic's retention period (time-based, e.g. 7 days, or size-based)
  is shorter than the maximum realistic duration a consumer could fall
  behind** -- retention is typically sized for "normal" operation, and an
  extended outage or a slow backfill/reprocessing job can easily exceed
  it without anyone having explicitly reasoned about that scenario.
- **A consumer was paused or stopped for longer than expected** (a
  deployment issue, an extended debugging session with the consumer
  intentionally halted) without anyone tracking how close that pause was
  getting to the retention limit.
- **A downstream system's own outage caused a consumer to intentionally
  slow down or pause** (backpressure) to avoid overwhelming the
  struggling downstream system, and that backpressure period alone
  exceeded retention before the downstream system recovered.
- **No alerting exists on consumer lag approaching the retention
  window**, so the team has no early warning before data loss actually
  occurs -- the first signal is often the consumer finding a gap after
  the fact.

## Diagnose

1. Compare the topic's actual configured retention (`retention.ms` or
   `retention.bytes`) against the consumer's lag duration at the time of
   the incident, calculated in the same units, to confirm retention
   expiry is genuinely what caused the gap (versus a different cause,
   like an accidental topic deletion/recreation).
2. Check consumer group offset history/logs for how long the consumer
   was actually paused or behind before catching up, to understand the
   real timeline relative to retention.
3. Check whether any alerting exists (or existed) on consumer lag
   thresholds, and whether it would have fired before the retention
   window was actually exceeded.
4. Determine the actual business impact of the specific lost messages
   (are they recoverable from another source, or permanently gone) to
   scope the severity of the incident.

## Fix

Size topic retention based on the worst-case realistic consumer-behind
scenario for the specific topic's criticality (a topic backing a
critical financial ledger needs much longer retention than a topic used
for ephemeral real-time notifications), not just "normal operation"
duration. Add alerting on consumer lag as a proportion of retention
window (e.g. alert when lag exceeds 50% of retention time remaining)
specifically so there's early warning before actual data loss, not just
after. For topics where losing any message is unacceptable, consider
tiered storage (if the Kafka distribution supports it) or a secondary,
longer-retention archival mechanism (a sink connector to object storage)
independent of the primary topic's operational retention.

## Pitfalls

Don't respond to one retention-related data loss incident by setting
retention extremely long for every topic as a blanket fix -- longer
retention has real storage cost implications cluster-wide; size it
deliberately per-topic based on actual criticality and realistic
worst-case consumer-behind duration, not uniformly maximized. Also don't
assume a consumer "caught up successfully" after an extended pause
actually processed everything -- explicitly verify no gap exists rather
than assuming successful resumption means completeness.

## Verify

After adjusting retention and alerting, simulate an extended consumer
pause in a non-production environment approaching (but not exceeding) a
realistic outage duration, and confirm the lag-based alert fires with
enough lead time to intervene before retention would actually be
exceeded. Confirm the specific topic's new retention setting is
consistent with its documented criticality/durability requirements.
