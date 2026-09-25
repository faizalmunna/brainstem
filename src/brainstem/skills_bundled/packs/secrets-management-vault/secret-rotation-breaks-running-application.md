---
name: secret-rotation-breaks-running-application
description: Rotating a static secret in Vault or a secrets manager breaks a running application because it doesn't pick up the new value until restarted, or fails during the rotation window.
triggers: ["secret rotation broke application", "credential rotation caused downtime", "app still using old secret after rotation", "rotating api key breaks service"]
permissions: ["READ"]
---

## Symptom

Rotating a secret (an API key, a database password) that a running
application depends on causes an outage or errors, either because the
application keeps using the cached old value and fails once it's
invalidated, or because there's a window during rotation where neither
the old nor the new value works consistently across all instances.

## Likely causes

- **The application reads the secret once at startup and caches it in
  memory for its entire lifetime**, with no mechanism to detect and
  reload a rotated value, so it keeps using the old (now invalid) secret
  until the process is restarted.
- **The rotation process invalidates the old secret before all
  application instances have picked up the new one**, creating a window
  where some instances (already updated) work and others (still on the
  old value) fail -- especially likely with many replicas and no
  coordinated rollout of the new secret.
- **A downstream system being authenticated to doesn't support having two
  valid credentials simultaneously during a transition window**, so
  there's no way to roll out the new secret gradually without a moment
  where the old one is invalidated while some callers haven't yet
  switched.
- **The rotation process itself doesn't verify the new secret actually
  works before invalidating the old one**, so a bad rotation (a typo, an
  incorrectly generated new credential) invalidates the working credential
  and leaves nothing functional.

## Diagnose

1. Check whether the application has any mechanism for detecting a
   changed secret at runtime (a file-watch, a periodic poll, a push
   notification from the secrets manager) versus reading once at startup.
2. Review the rotation process's sequencing -- does it invalidate the old
   secret immediately upon generating the new one, or does it maintain
   overlap until confirming the new one is in use everywhere?
3. Check whether the downstream authenticated system supports multiple
   simultaneously valid credentials (many systems do support this
   specifically to enable safe rotation) and whether the rotation process
   actually takes advantage of that support.
4. Review logs from the rotation window across all application instances
   to identify which specific instances failed and correlate with when
   each actually picked up the new secret.

## Fix

Implement live secret reloading in the application (watching for changes
via the secrets manager's notification mechanism, or periodic polling
with reasonable frequency) rather than requiring a restart to pick up a
new value. Design rotation to maintain overlap -- generate and verify the
new secret works, roll it out to all application instances, confirm all
instances are using it, and only then invalidate the old secret --
rather than invalidating immediately upon generating the new one. For
systems that support it, use dual-credential support explicitly during
the rotation window rather than a hard cutover.

## Pitfalls

Don't automate secret rotation without first verifying the application
actually supports live reloading -- rolling out automated rotation
against an application that only reads secrets at startup guarantees
recurring outages timed to the rotation schedule. Also don't skip
verifying the new secret actually works before invalidating the old one,
even under time pressure to complete a rotation quickly -- a failed
verification step here is exactly what prevents a rotation from becoming
an outage.

## Verify

Perform a rotation in a non-prod environment and confirm the application
picks up the new secret without requiring a restart, with zero failed
requests during the transition. Confirm the old secret is only
invalidated after confirming (via logs/metrics) that all instances are
successfully using the new one.
