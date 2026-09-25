---
name: release-stuck-pending-upgrade-blocks-further-releases
description: A Helm release is stuck showing status pending-upgrade or pending-install after a failed upgrade, and every subsequent helm upgrade or rollback attempt is refused.
triggers: ["helm release stuck pending-upgrade", "another operation (install/upgrade/rollback) is in progress", "helm upgrade refuses to run stuck release", "helm pending-install stuck", "cannot patch helm release already in progress"]
permissions: ["READ"]
---

## Symptom
A previous `helm upgrade` was interrupted (CI job killed, network drop,
Tiller/controller restart in older setups, or the upgrade itself timed
out waiting on a hook or a resource to become ready), and now `helm
status <release>` shows `pending-upgrade` (or `pending-install`,
`pending-rollback`) indefinitely. Every subsequent `helm upgrade` or
`helm rollback` against that release fails immediately with an error like
`another operation (install/upgrade/rollback) is in progress`, even
though nothing is actually running.

## Likely causes
1. **The Helm client/CI job that initiated the upgrade was killed or lost
   connectivity before the operation completed**, so Helm's release
   history was written with a `pending-*` status (Helm records intent
   before completion) but nothing ever transitioned it to `deployed` or
   `failed` -- there is no active lock, just a stale status value in the
   stored release secret/configmap.
2. **A pre-upgrade or post-upgrade hook is hanging** (a Job that never
   completes because of a bad image, a missing dependency, or a resource
   that never reaches Ready), and the `helm upgrade` command is still
   technically running client-side with `--wait`, actively blocking a
   second invocation -- this looks identical to case 1 from `helm
   status` alone but the underlying cause is different (still-running
   vs. actually-abandoned).
3. **Multiple CI pipelines or engineers triggering `helm upgrade` against
   the same release concurrently**, where the second invocation is
   correctly refused because the first is genuinely still in progress --
   mistaking this for a stuck release and force-fixing it mid-flight
   causes a real race condition on the same resources.
4. **A crashed Helm process left the release secret in `pending-*` state
   after `--atomic` was expected to auto-rollback but the rollback itself
   also failed or was interrupted**, leaving the release in a state
   between two inconsistent revisions with no clean automatic recovery
   path.

## Diagnose
- First confirm nothing is actually still running: check the CI system
  for an in-flight job against this release, and run `kubectl get jobs
  -n <namespace>` / `kubectl get pods -n <namespace>` for anything tied
  to a Helm hook (`helm.sh/hook` annotation) that's still active or
  recently failed -- do this before touching anything, to rule out case
  3.
- Run `helm history <release>` and look at the most recent revision's
  status and timestamp -- a `pending-upgrade` entry with a timestamp far
  in the past (well beyond any reasonable upgrade duration) confirms it's
  abandoned, not in-flight.
- Run `kubectl get secret -n <namespace> -l
  owner=helm,name=<release> --sort-by=.metadata.creationTimestamp` (or
  the equivalent configmap-based storage backend) to see the raw release
  revision objects Helm tracks, confirming which revision is marked
  pending.
- Check whether `--atomic` was used on the original upgrade command (CI
  pipeline definition or deploy script) -- this changes whether the
  expected recovery path was an automatic rollback that itself may have
  failed.

## Fix
- If confirmed abandoned (not actually in-flight), the supported recovery
  is `helm rollback <release> <last-good-revision>`, which in most
  current Helm versions is able to roll back out of a `pending-*` state
  back to the last `deployed` revision, clearing the stuck status as part
  of the rollback.
- If rollback itself refuses or fails, the direct-but-riskier fix is to
  edit the release's stored status: locate the current revision's
  Secret/ConfigMap (`kubectl get secret sh.helm.release.v1.<release>.v<N>
  -n <namespace>`), and use `helm` tooling (some versions expose `helm
  release status` fixes) or, as a last resort, patch the stored status
  field back to `failed` so Helm's own next-operation check allows a new
  `helm upgrade` to proceed -- treat this as an escape hatch, not a
  routine step, since it bypasses Helm's own consistency bookkeeping.
- Going forward, run upgrades with `--atomic --timeout <realistic
  duration>` so a failed upgrade automatically rolls back to the last
  good state instead of leaving a `pending-*` release, and ensure CI
  jobs running `helm upgrade` have their own timeout longer than Helm's
  `--timeout` so the CI runner isn't the thing killing the Helm process
  mid-operation.
- Investigate and fix the underlying hook/resource-readiness failure that
  caused the original upgrade to hang or fail, since resolving the stuck
  status without fixing the root cause just reproduces the same stuck
  state on the next deploy.

## Pitfalls
- Manually deleting the release's Secret/ConfigMap objects entirely
  (instead of correcting the status field or using rollback) destroys
  Helm's revision history for that release, which removes the ability to
  roll back to any prior revision and can orphan resources Helm no
  longer has any record of managing.
- Force-resolving a stuck release without first ruling out "it's actually
  still running" (case 3) can cause two concurrent operations to fight
  over the same resources, producing a worse and harder-to-diagnose
  inconsistent state than the original stuck status.

## Verify
After recovery, run `helm status <release>` and confirm it reports
`deployed` (not any `pending-*` or `failed` state), then run a normal
`helm upgrade --dry-run` against the release and confirm it succeeds
without the "another operation is in progress" error, proving the lock
condition is actually cleared and not just cosmetically different.
