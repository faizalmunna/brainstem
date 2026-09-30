---
name: long-lived-static-cloud-credentials-never-rotated-or-scanned
description: A cloud access key or service account key turns out to be years old, never rotated, and was found embedded in a repository or CI log rather than caught proactively.
triggers: ["this access key is three years old", "found a cloud credential committed to the repo", "static key never rotated since it was created", "secret scanner would have caught this months ago"]
permissions: ["READ"]
---

## Symptom

A security review turns up a long-lived static credential (an IAM access
key, a service account JSON key, a storage connection string) that has
never been rotated since creation -- sometimes years old -- and, in the
worse version of this symptom, the credential is discovered sitting in a
git repository, a CI job log, or a container image layer rather than
being flagged proactively by any internal control before that exposure
happened.

## Likely causes

- **Static long-lived credentials were issued because the workload
  needing access predates or doesn't integrate with the provider's
  short-lived/federated credential mechanisms** (workload identity
  federation, instance-role-based temporary credentials), so a static
  key was the path of least resistance at the time and nothing since has
  revisited that decision.
- **No credential rotation policy or automation exists**, so even where
  rotation is technically possible, it depends on someone remembering to
  do it manually, which for a credential that "just works" has no
  natural trigger to ever happen.
- **No secret-scanning is running against source repositories, CI/CD
  pipeline logs, or container image layers**, so a credential
  accidentally committed or printed to a log has no automated detection
  path and relies entirely on someone noticing by chance or an external
  party finding it first.
- **The credential was created with broad permissions "to be safe" at
  provisioning time**, so its accidental exposure has a much larger
  blast radius than if it had been scoped narrowly to the specific
  resource and actions the workload actually needed.

## Diagnose

1. Enumerate all static/long-lived credentials across every account
   (IAM access keys, service account keys, connection strings, API
   keys) and pull each one's creation date and last-rotated date --
   flag anything exceeding a defined maximum age (commonly 90 days for
   high-privilege credentials).
2. Check whether any secret-scanning tool currently runs against source
   repositories (including full git history, not just the current
   branch tip), CI/CD pipeline logs, and container registries -- and if
   one exists, check its actual finding history and whether findings
   were acted on.
3. For any credential found exposed in a repository, log, or image,
   check the provider's access logs for usage of that credential from
   any source outside expected infrastructure, to determine whether it
   was actually exploited or only exposed.
4. For each long-lived credential found, check whether the workload
   using it could instead use the provider's short-lived/federated
   credential mechanism (instance profile roles, workload identity
   federation, managed identities) -- if so, the static key is
   avoidable entirely, not just something to rotate.

## Fix

Wherever the provider offers a short-lived or federated credential
mechanism for the workload's context (compute-instance roles, workload
identity federation for CI/CD, managed identities), migrate off static
keys entirely rather than just rotating them, since eliminating the
long-lived secret removes the exposure risk rather than just bounding
it. For any static credential that genuinely can't be eliminated,
enforce automatic rotation on a defined schedule via the provider's
native rotation support or a secrets manager integration, and scope its
permissions to the minimum the workload needs so an eventual exposure
has bounded impact. Deploy secret-scanning across source repositories
(full history), CI/CD logs, and container images as a blocking check in
the pipeline (failing the build/commit on a detected secret) rather than
an after-the-fact report, so exposure is caught before it merges rather
than discovered later.

## Pitfalls

Don't treat "we now scan for secrets going forward" as sufficient
remediation for a credential already found exposed -- if a static
credential was ever committed to a repository, its full git history
(not just the latest commit) has propagated it to every clone, fork, and
CI cache; the credential must be revoked and reissued, not just removed
from the current file state, since deleting a file doesn't remove it
from history.

## Verify

Confirm the exposed credential has been fully revoked (not just
rotated) and that any workload depending on it has been updated to use
its replacement, either a new scoped credential or a short-lived
mechanism, with zero remaining references to the old credential value
anywhere in active configuration. Run the secret-scanning tool against
the full repository history and confirm it flags the historical exposure,
then confirm a deliberately committed test secret in a lower environment
is caught and blocks the pipeline before merge.
