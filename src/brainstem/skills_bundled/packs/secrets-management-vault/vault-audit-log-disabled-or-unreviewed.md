---
name: vault-audit-log-disabled-or-unreviewed
description: A security incident investigation finds Vault's audit logging was disabled, misconfigured, or simply never reviewed, leaving no record of which secrets were accessed and by whom.
triggers: ["vault audit log not enabled", "cannot tell who accessed secret", "vault audit device misconfigured", "no visibility into vault access history"]
permissions: ["READ"]
---

## Symptom

Investigating a suspected credential compromise or unusual access
pattern, the team goes to check Vault's audit log for who accessed a
specific secret and when -- and discovers audit logging was never
enabled, was enabled but pointed at a destination nobody actually
monitors, or was disabled at some point without anyone noticing.

## Likely causes

- **Audit logging was never enabled during initial Vault setup**, since
  it's not on by default and requires an explicit audit device
  configuration step that's easy to overlook when focus is on getting
  Vault functionally operational.
- **An audit device was configured but writes to a destination
  (a local file, a specific log aggregator) that isn't actually monitored
  or retained long enough** to be useful during a delayed investigation,
  effectively making the audit trail exist but be practically useless.
- **A previously-working audit device silently stopped functioning**
  (disk full, a downstream log pipeline failure) -- Vault's behavior when
  ALL audit devices fail is actually to block all requests by design
  (fail-closed), but if only one of multiple configured audit devices
  fails, this can go unnoticed since Vault continues operating using the
  remaining device(s).
- **Audit logs exist and are being written correctly, but nobody actually
  reviews them proactively or has alerting on suspicious patterns** -- the
  data exists but provides no real security value if it's never looked at
  except reactively, after an incident is already suspected.

## Diagnose

1. Check Vault's currently configured audit devices (`vault audit list`
   or equivalent) and confirm at least one is actually enabled and
   functioning.
2. For each configured audit device, verify its destination is actually
   receiving data (check recent log entries exist and are current, not
   just that the configuration exists).
3. Check retention policy on wherever audit logs are stored -- confirm
   logs are kept long enough to support a realistic investigation
   timeline (which can be weeks to months after an actual compromise
   occurred).
4. Check whether any alerting or regular review process exists on audit
   log content, versus the logs existing purely as a reactive resource.

## Fix

Enable at least one (ideally more than one, for redundancy) audit device
pointed at a monitored, appropriately retained destination -- a
centralized log aggregation system the security/ops team already
monitors, not an isolated local file. Set up basic alerting on
suspicious audit log patterns (access to particularly sensitive secret
paths, access from unexpected identities/IPs, unusual volume) rather than
treating the audit log as purely a forensic resource reviewed only after
an incident is already suspected. Periodically verify audit devices are
actually still functioning (a synthetic test entry, a periodic check)
rather than assuming a one-time setup remains correct indefinitely.

## Pitfalls

Don't configure only a single audit device without understanding Vault's
fail-closed behavior -- if that one device becomes unavailable (disk
full, network issue), Vault will block ALL requests rather than silently
continuing without audit logging, which is the correct security-
prioritizing behavior but can cause an unexpected outage if the audit
destination isn't as reliable as Vault itself; configure multiple audit
devices for redundancy specifically to avoid this failure mode causing
an outage.

## Verify

Perform a test secret access and confirm it appears promptly in the
configured audit log destination with the expected identity/path detail.
Simulate one audit device becoming unavailable (in a non-production
environment) and confirm Vault's behavior matches expectations (either
continuing via a redundant device, or intentionally blocking if that's
the only device, consistent with the fail-closed design).
