---
name: structured-logging-inconsistency
description: Logs across (or even within) a service use inconsistent formats/field names, making search, correlation, and dashboarding unreliable.
triggers: ["logs are inconsistent", "can't search logs reliably", "log field names differ", "log format varies by service", "structured logging"]
permissions: ["READ"]
---

## Symptom

Searching or filtering logs (in Elastic, Loki, Datadog, CloudWatch
Insights) for something that should be simple -- "every log line for
request X," "every error with this user ID" -- misses entries because the
same conceptual field is named differently across log lines (`user_id`
vs. `userId` vs. `uid`), or is sometimes present as a structured field and
sometimes only interpolated into a free-text message string.

## Likely causes

- **No shared logging schema/convention was ever agreed on** -- each
  service or even each engineer picked field names independently.
- **Mixing plain-text and structured (JSON) logging** in the same
  service, often because a third-party library logs in plain text while
  application code logs structured JSON, and both get shipped to the same
  pipeline without normalization.
- **A field's type is inconsistent across call sites** -- sometimes a
  timestamp is an ISO string, sometimes a Unix epoch number, sometimes a
  epoch in milliseconds vs. seconds -- breaking time-based queries and
  sorting.
- **Correlation identifiers (trace ID, request ID) are only interpolated
  into the message text** ("processing request abc123") instead of being
  a first-class structured field, so they can't be filtered on directly.
- **A logging library upgrade or migration was partial** -- some call
  sites still use the old API/format, others use the new one, and nobody
  audited for the gap.

## Diagnose

1. Pull a sample of log lines across the services involved and diff their
   field sets/naming for the same conceptual data (user, request,
   timestamp, severity) -- the inconsistency is usually visible within a
   handful of samples.
2. Check whether the correlation ID (trace/request ID) is a structured,
   filterable field on every line that should have it, or only sometimes
   present, or only present inside the message text.
3. Check timestamp fields specifically for type/unit consistency (string
   vs. number, seconds vs. milliseconds) since this silently breaks
   chronological queries without an obvious error.
4. Identify whether the inconsistency is cross-service (different teams,
   no shared standard) or within one service (partial migration, mixed
   libraries) -- the fix differs by which one it is.

## Fix

Adopt one structured logging schema (field names, types, required fields
like timestamp/level/service/trace_id) as an explicit, documented
convention, and enforce it either via a shared logging wrapper library
that every service imports (rather than each team configuring their own
logger) or via a normalization step in the log pipeline (a processor/
transform that renames known-inconsistent fields at ingestion). Make the
correlation ID a structured field on every log line by default, injected
by middleware/interceptor rather than left to each call site to remember.
For a partial migration, audit remaining call sites specifically (grep for
the old logging API/pattern) rather than assuming a library upgrade
propagated everywhere.

## Pitfalls

Don't solve this by writing ad hoc per-query field-name synonyms in every
dashboard/alert instead of fixing the source -- that's a workaround that
has to be repeated in every new dashboard forever and silently breaks
again whenever a new inconsistent field appears. Also be careful that a
shared logging wrapper doesn't become so opinionated it discourages
service-specific structured fields that are genuinely useful -- the goal
is a consistent *core* schema, not eliminating all per-service fields.

## Verify

Run the same correlation query (e.g., "every log line for trace ID X")
across all affected services after the fix and confirm it returns a
complete, correctly ordered set with no missing hops. Spot-check a new
service or a fresh deploy to confirm it inherits the shared schema by
default rather than requiring each new codebase to remember the
convention manually.
