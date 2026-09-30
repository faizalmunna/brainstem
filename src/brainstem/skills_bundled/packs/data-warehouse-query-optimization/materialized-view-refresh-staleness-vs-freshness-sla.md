---
name: materialized-view-refresh-staleness-vs-freshness-sla
description: A materialized view or summary table returns outdated results because its refresh schedule doesn't match the freshness downstream consumers actually require.
triggers: ["materialized view showing old data", "dashboard numbers out of date", "summary table stale", "materialized view refresh schedule wrong", "data freshness sla undefined"]
permissions: ["READ"]
---

## Symptom
Someone notices a dashboard, report, or downstream table built on a
materialized view (or a manually scheduled summary/rollup table) shows
numbers that don't match the live source data -- sometimes discovered
only when a stakeholder flags a discrepancy, not through any automated
alert, because no one had defined what "fresh enough" actually means for
that consumer.

## Likely causes
1. **The refresh schedule was set once based on engineering convenience**
   (e.g. "nightly batch, matches the rest of the ETL window") rather than
   the actual business requirement, and consumer needs changed since
   (a report that used to be reviewed weekly is now checked intra-day).
2. **No documented freshness SLA exists at all**, so there's no shared
   definition of "stale" to alert on -- staleness is only caught
   informally when a human happens to notice a discrepancy.
3. **The materialized view's underlying refresh silently failed or fell
   behind** (a scheduled `REFRESH`/`ALTER MATERIALIZED VIEW` job errored,
   or an incremental refresh's watermark logic stalled) and nothing
   monitors the actual data recency, only whether the refresh job's
   scheduler reported success.
4. **Multiple consumers of the same materialized view have different
   freshness needs**, and the refresh cadence was tuned for the loosest
   or the tightest one without anyone reconciling that this one schedule
   now over- or under-serves the others.

## Diagnose
- Compare the materialized view's last-refresh timestamp (Snowflake:
  `SYSTEM$STREAM_HAS_DATA`/materialized view metadata; BigQuery:
  `INFORMATION_SCHEMA.MATERIALIZED_VIEWS.last_refresh_time`; Redshift:
  `STV_MV_INFO`) against the current time and against the underlying base
  table's most recent write timestamp to compute actual observed lag.
- Ask (or find existing documentation for) each known downstream
  consumer -- dashboard, scheduled export, another pipeline -- what
  staleness they can tolerate; if no answer exists anywhere, that's the
  root problem, not a diagnostic dead end.
- Check the refresh job's execution history/logs for failures or
  skipped runs, not just its schedule definition -- a job configured to
  run hourly that's silently been failing for days looks identical to a
  working hourly job unless you check actual run outcomes.
- For incremental refresh, check whether the refresh predicate/watermark
  is advancing correctly (e.g. a stream-based refresh on Snowflake whose
  underlying stream has gone stale past its retention window will stop
  capturing changes silently).

## Fix
Establish and document an explicit freshness SLA per materialized
view/summary table (e.g. "under 15 minutes lag" or "refreshed by 6am
daily"), derived from actual consumer requirements gathered directly
rather than assumed, and encode it as a monitored property: alert when
observed lag (current time minus last successful refresh reflected in
data) exceeds the SLA, not just when the refresh job itself errors.
Where different consumers genuinely need different freshness, split into
tiers -- a fast, cheaper-to-refresh near-real-time view for the
latency-sensitive consumer and a separate, more expensive fully-
reconciled nightly rollup for the rest -- rather than forcing one
schedule to serve incompatible needs. Where near-real-time freshness is
required, prefer an incremental/streaming refresh mechanism over
frequent full-table `REFRESH`, since full rebuilds at high frequency are
often too expensive to sustain at the cadence the SLA requires.

## Pitfalls
Tightening the refresh interval as a reflexive fix for a staleness
complaint, without checking the cost impact, can silently multiply
warehouse compute spend (a materialized view refreshed every 5 minutes
instead of hourly is 12x the refresh compute) for a freshness improvement
nobody actually asked for -- validate the real requirement before paying
for more frequent refreshes. Also, don't conflate "the refresh job
succeeded" with "the data is fresh": a successful incremental refresh
that processed zero new rows because its watermark stalled looks
identical in job-success monitoring to a healthy refresh with no new
data to process.

## Verify
After setting the SLA and monitoring, confirm alerting actually fires
by intentionally checking (or synthetically simulating) a refresh delay
exceeding the SLA threshold, and confirm the documented SLA and its
actual observed lag are both visible somewhere consumers and on-call
engineers can check without asking the pipeline's original author.
