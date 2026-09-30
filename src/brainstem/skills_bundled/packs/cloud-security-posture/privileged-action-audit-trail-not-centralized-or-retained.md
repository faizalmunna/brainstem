---
name: privileged-action-audit-trail-not-centralized-or-retained
description: A post-incident investigation into privileged account activity fails because audit logs weren't centralized or weren't retained long enough to cover the relevant window.
triggers: ["we can't reconstruct what the attacker did", "logs were rotated before we could investigate", "audit trail is scattered across accounts", "retention period too short for the incident timeline"]
permissions: ["READ"]
---

## Symptom

During a real incident investigation (suspected compromise, insider
misuse, or a compliance-mandated forensic review), the team goes looking
for a clear record of privileged actions taken across the affected
period and finds the trail is incomplete: logs from some accounts are
missing entirely, logs from different accounts/services live in
different places with no unified query path, or the relevant events fell
outside the configured retention window and were already purged.

## Likely causes

- **Native audit logging is enabled per-account/per-project with default
  settings**, and default retention windows are often shorter than the
  realistic delay between a compromise occurring and it being discovered
  (which can be weeks to months), so by investigation time the earliest
  relevant events are already gone.
- **Logs exist but are scattered across each individual account's own
  log store with no aggregation into a central, cross-account
  queryable system**, so reconstructing a single actor's actions that
  spanned multiple accounts requires manually pulling and correlating
  logs from each one separately, which is slow and error-prone exactly
  when speed matters most.
- **Logging was enabled for management/control-plane events but not for
  data-plane access to sensitive resources** (object-level access to a
  storage bucket, row-level database query logging), so the audit trail
  shows that a privileged identity assumed a role but not what it
  actually did with the access, which is often the detail the
  investigation needs most.
- **Log integrity isn't protected** -- logs are stored in a location the
  same privileged identities being audited could plausibly modify or
  delete, so even where logs exist, their trustworthiness as forensic
  evidence is undermined if a sophisticated actor could have tampered
  with them.

## Diagnose

1. Check the configured retention period on every audit log source
   (CloudTrail, Cloud Audit Logs, Activity Log, and any workload-level
   logging) against a realistic detection-to-investigation timeline for
   your environment -- if retention is shorter than your typical
   time-to-detect, that's an active gap right now, not just a
   theoretical one.
2. Attempt to answer a realistic investigative question ("show me every
   privileged action taken by identity X across all accounts in the
   last 90 days") using current tooling, and time how long it takes and
   how many separate systems must be queried -- this concretely reveals
   the centralization gap.
3. Check whether data-plane/object-level logging is enabled for
   sensitive resource types specifically, not just control-plane API
   call logging, since many providers disable the more detailed
   (and higher-volume/higher-cost) data-plane logging by default.
4. Check the IAM permissions on the log storage destination itself --
   confirm privileged account holders being audited don't also have
   delete/modify permissions on the log store, which would let a
   compromised privileged account cover its own tracks.

## Fix

Route audit logs from every account into a centralized, cross-account
log aggregation destination (a dedicated logging account/project with
restricted access, or a SIEM) as a standing architectural requirement
applied at account-creation time via IaC/landing-zone automation, not as
a per-account opt-in. Set retention to match a realistic
detection-to-investigation timeline (commonly 1 year or more for
security-relevant logs, informed by your actual historical time-to-
detect), and enable data-plane logging for genuinely sensitive resource
types even though it costs more, scoped to the resources where it
matters rather than blanket-enabled everywhere. Lock down the
centralized log store with its own restrictive IAM policy, ideally in a
separate account from the workloads being logged, so the identities
being audited cannot alter their own trail.

## Pitfalls

Don't assume enabling the log source is sufficient without checking who
can write to and, critically, who can delete from the log destination --
a centralized log store with weak access control is only marginally
better than no centralization, since a sufficiently privileged
compromised identity could still purge the evidence.

## Verify

Re-run the realistic investigative query ("show every privileged action
by identity X across all accounts over N days") and confirm it can be
answered from the centralized store alone within a reasonable time,
without manually querying individual accounts. Confirm the log store's
access policy denies delete/modify permissions to the workload accounts'
privileged identities, and confirm the configured retention period
against the log store's actual oldest available entry to verify
retention is functioning as configured, not just configured on paper.
