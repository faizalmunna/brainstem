---
name: helm-rollback-fails-due-to-manual-cluster-drift
description: A helm rollback to a previous revision errors out or leaves resources in an inconsistent state because something was changed on the cluster outside of Helm.
triggers: ["helm rollback failed", "helm rollback left resources inconsistent", "kubectl edit then helm rollback broke", "helm history revision does not match cluster state", "helm rollback stuck"]
permissions: ["READ"]
---

## Symptom
Someone ran `kubectl edit`, `kubectl patch`, or `kubectl scale` directly
against a resource Helm manages (often during an incident, to get a fix
out fast), and later a `helm rollback <release> <revision>` either fails
outright with an error like immutable field conflicts, or "succeeds" but
leaves the cluster in a state that matches neither the target revision
nor the manually-patched state -- e.g. a manually added label survives
the rollback, or a manually removed field silently reappears in a
half-applied way.

## Likely causes
1. **Helm rollback is a 3-way-merge-unaware diff against its own stored
   release manifest**, not a live reconciliation against actual cluster
   state -- it computes a patch from "what Helm thinks is currently
   deployed" (the last stored release) to "the target revision," and
   applies that patch to whatever is actually on the cluster. If the
   live object diverged from what Helm thinks is there, the patch is
   computed against a stale baseline and can produce nonsensical merges.
2. **A manual change to an immutable field** (e.g. a Job's
   `spec.selector`, a PVC's `spec.resources.requests.storage` shrink, or
   a Deployment's `spec.selector.matchLabels`) that Kubernetes itself
   rejects on update -- the rollback fails at the API server level
   because the target revision's manifest can't be applied over the
   drifted live object without deleting and recreating the resource,
   which Helm rollback doesn't do automatically.
3. **Manually deleted resource that Helm still tracks in its release
   secret/configmap**, so rollback tries to update a resource that no
   longer exists, sometimes succeeding by recreating it in the target
   revision's state and sometimes failing depending on resource type and
   what else references it.
4. **A manually-applied `kubectl` change added an annotation/label Helm
   itself uses for ownership tracking** (`meta.helm.sh/release-name`,
   `app.kubernetes.io/managed-by`) inconsistently, causing Helm's
   ownership check to reject the rollback with a "invalid ownership
   metadata" error because it now looks like the resource belongs to a
   different release or was created outside Helm entirely.

## Diagnose
- Run `helm get manifest <release> --revision <N>` for both the current
  and target revision, and separately `kubectl get <resource> -o yaml`
  for the live object -- diff live-vs-current-revision first; any
  difference there is drift Helm doesn't know about, independent of the
  rollback itself.
- Check `kubectl get <resource> -o yaml | grep -A3 annotations` for
  `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace` --
  if these are missing or point to an unexpected release, Helm's
  ownership check is the likely failure point.
- Read the exact rollback error message: `Invalid value ... field is
  immutable` points to cause 2; `annotation validation error` or `missing
  key` points to ownership metadata (cause 4); a generic patch/apply
  conflict without a specific field named is more consistent with cause
  1 (stale baseline).
- Run `helm history <release>` and correlate timestamps against
  `kubectl get events --sort-by=.lastTimestamp` around the suspected
  manual change window to confirm a `kubectl edit`/`patch`/`scale` event
  happened between the last Helm operation and the rollback attempt.

## Fix
- Treat any resource under Helm management as off-limits for direct
  `kubectl edit`/`patch` even during incidents -- if an emergency patch
  is unavoidable, follow it immediately with a `helm upgrade` (not just a
  rollback later) that captures the same change in the chart/values, so
  Helm's stored state and live state are reconciled right away rather
  than left to diverge until the next rollback attempt.
- For an immutable-field conflict, delete and recreate the specific
  resource rather than expecting rollback to handle it: `kubectl delete
  <resource> <name>` followed by `helm rollback` (or `helm upgrade`) so
  the target revision's manifest is applied to a clean slate instead of
  patched onto an incompatible live object. Confirm nothing else
  references the resource by identity (e.g. a Service's ClusterIP being
  intentionally stable) before deleting.
- If ownership annotations were manually stripped or altered, restore
  them to match the actual owning release before retrying (`kubectl
  annotate --overwrite ... meta.helm.sh/release-name=<release>
  meta.helm.sh/release-namespace=<namespace>` plus the matching
  `app.kubernetes.io/managed-by: Helm` label), or use `helm adopt`-style
  patterns / `helm upgrade --take-ownership` where available in the Helm
  version in use.
- After any known drift incident, run `helm diff upgrade` (via the
  `helm-diff` plugin) against the current chart/values before the next
  real change, specifically to surface drift as a diff review step
  rather than discovering it mid-rollback.

## Pitfalls
- Deleting and recreating a resource to work around an immutable-field
  conflict on a stateful resource (a PVC, a Service with a pinned
  ClusterIP or LoadBalancer IP) can cause real data loss or an IP/DNS
  change with downstream impact -- always check the resource kind's
  semantics before defaulting to delete-and-recreate as the fix.
- Restoring Helm's ownership annotations to "fix" the rollback without
  first confirming which release SHOULD actually own the resource can
  paper over a genuine multi-release naming collision instead of
  revealing it (see the release-name-collision-in-shared-namespace
  skill).

## Verify
After the rollback completes, run `helm get manifest <release>` and
`kubectl get <resource> -o yaml` again and diff them directly -- they
should match on every field Helm manages (some system-populated fields
like `resourceVersion`/`status` will legitimately differ). Also run
`helm status <release>` and confirm it reports the expected target
revision as deployed, not stuck in a pending or failed state.
