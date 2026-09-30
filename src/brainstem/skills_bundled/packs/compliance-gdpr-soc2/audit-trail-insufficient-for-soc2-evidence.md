---
name: audit-trail-insufficient-for-soc2-evidence
description: A SOC 2 audit fails or is delayed because the application's audit logging doesn't capture enough detail to prove a specific control (who accessed what, when, and why) was actually being followed.
triggers: ["soc2 audit evidence insufficient", "audit trail missing required detail", "cannot prove access control soc2", "compliance audit failed on logging evidence"]
permissions: ["READ"]
---

## Symptom

During a SOC 2 (or similar compliance framework) audit, an auditor
requests evidence that a specific control was actually operating (for
example, that access to sensitive customer data is logged and reviewed)
-- and the available audit logs don't capture enough detail to actually
demonstrate this: missing who performed an action, missing timestamps,
missing enough context to distinguish legitimate access from unusual
access, or simply not retained long enough to cover the audit period.

## Likely causes

- **Logging was implemented for operational/debugging purposes**
  (capturing what the application did, for troubleshooting) rather than
  for compliance evidence purposes (capturing who did what, for
  accountability), so it lacks fields a compliance control actually
  requires (a specific user identity, not just a generic system actor).
- **Log retention is shorter than the audit period being evaluated**, so
  even if logging was adequate, the specific evidence needed for an
  earlier part of the audit window has already been purged.
- **The control being audited was defined (in a policy document) without
  verifying the actual logging implementation could produce evidence for
  it** -- the policy says "all access to customer PII is logged and
  reviewed monthly" but the logging implementation doesn't actually
  capture PII-specific access events distinctly from general application
  activity.
- **Logs exist but aren't organized/searchable in a way that lets someone
  actually produce the specific evidence an auditor requests within a
  reasonable time**, even if the raw data technically exists somewhere.

## Diagnose

1. For the specific failed/delayed control, read exactly what evidence
   the auditor requested and compare against what the current logging
   actually captures field-by-field.
2. Check log retention configuration against the audit period being
   evaluated to confirm whether a retention gap (not a capture gap) is
   the actual issue.
3. Review the written policy/control description for the specific
   control and confirm whether it accurately describes what the system
   is actually capable of evidencing, or was written aspirationally
   without verification against the real implementation.
4. Assess how long it took (or would take) to actually produce the
   requested evidence from existing logs, to determine whether it's a
   capture problem, a retention problem, or a searchability/tooling
   problem.

## Fix

Add the specific missing fields to audit logging for the control in
question (actual user identity, specific resource/data category
accessed, timestamp, outcome) so future evidence requests can be
satisfied directly. Extend log retention to cover at least the full
audit period for any control-relevant logs, distinct from
operational/debugging logs that may have a shorter, separate retention
policy. Review and align written policy/control descriptions with what
the logging implementation can actually evidence, rather than leaving a
gap between documented policy and actual capability. Build or adopt
tooling that makes producing specific evidence (a report of all access to
a given data category in a given window) fast and reliable, rather than
requiring ad hoc log searching under audit time pressure.

## Pitfalls

Don't write compliance policy language describing controls more
stringent than what the system can actually evidence, purely to sound
thorough -- an unverifiable policy claim is worse for an audit than an
accurately-scoped one, since it creates a documented commitment the
organization can't actually prove it met.

## Verify

Before the next audit cycle, run a mock evidence request against the
updated logging for the specific previously-failed control and confirm
the needed evidence can actually be produced within a reasonable
timeframe, covering a period at least as long as a real audit would
require.
