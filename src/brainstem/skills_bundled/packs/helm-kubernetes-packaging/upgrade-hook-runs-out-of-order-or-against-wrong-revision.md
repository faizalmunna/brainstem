---
name: upgrade-hook-runs-out-of-order-or-against-wrong-revision
description: A pre-upgrade or post-upgrade Helm hook Job runs at the wrong point in the release, such as a database migration executing against the previous schema.
triggers: ["helm hook ran at wrong time", "pre-upgrade hook ran before old pods drained", "helm migration job ran against old code", "post-upgrade hook race condition", "helm hook weight ordering wrong"]
permissions: ["READ"]
---

## Symptom
A chart uses a Helm hook (commonly a `pre-upgrade` Job running a database
migration, or a `post-upgrade` Job running a smoke test/cache warm) and
something about its timing is wrong: a migration hook runs but the new
application pods that need the migrated schema start before the
migration Job finishes, or the migration runs against the still-running
OLD version's assumptions because it fired before old pods were scaled
down, or two hooks that must run in a specific relative order (e.g.
migrate-then-seed) execute concurrently or reversed.

## Likely causes
1. **No `helm.sh/hook-weight` set (or an incorrect one) on hooks that
   must run in a specific relative order** -- when multiple hooks share
   the same hook type (e.g. two `pre-upgrade` Jobs), Helm has no
   guaranteed ordering between them unless `hook-weight` annotations are
   set (lower weights run first); without it, ordering is effectively
   undefined/implementation-dependent and can change between Helm
   versions or even between runs.
2. **Misunderstanding which hook type actually blocks pod rollout** --
   `pre-upgrade` runs before ANY new resources are updated, which is
   correct for "migrate schema before new code needs it," but a
   `post-upgrade` hook runs after Kubernetes resources are updated,
   which does NOT mean after new pods are fully ready/serving traffic --
   a `post-upgrade` smoke test can run against a Deployment that's still
   mid-rollout with a mix of old and new pods behind the same Service.
3. **Missing or default `helm.sh/hook-delete-policy`**, causing a hook
   Job from a previous release to still exist when the next upgrade's
   hook tries to create a same-named Job -- Kubernetes Job specs are
   largely immutable, so this produces a hook failure that looks like a
   timing/ordering bug but is actually a leftover-resource collision
   from the prior run.
4. **Hook Job lacks `--wait`-equivalent blocking behavior for what it
   depends on** -- e.g. a `pre-upgrade` migration Job assumes the
   database is reachable, but if the database itself is also part of
   this same chart/release and is mid-upgrade, the hook can race against
   its own dependency with nothing in Helm's model expressing "wait for
   this other resource to be ready first," since hooks only order
   relative to the release lifecycle phase, not relative to arbitrary
   other resources' readiness.

## Diagnose
- Run `kubectl get jobs -n <namespace> -l
  "helm.sh/hook"  --sort-by=.metadata.creationTimestamp` right after an
  upgrade and check actual creation/completion timestamps against the
  Deployment's rollout timestamps (`kubectl rollout history
  deployment/<name>`) to see the real observed order, not the assumed
  one.
- Grep all templates for `helm.sh/hook` and `helm.sh/hook-weight`
  annotations across the chart -- list every hook, its type(s), and its
  weight (or lack of one) in one place to reason about relative ordering
  explicitly rather than per-file.
- Check `helm.sh/hook-delete-policy` on each hook Job --
  `before-hook-creation` (recommended for most cases) versus
  `hook-succeeded`/`hook-failed`/unset, and confirm it matches whether
  the team wants old hook Jobs cleaned up automatically before the next
  run.
- Re-run the upgrade with `helm upgrade --debug` and watch the hook
  execution log lines in order; separately watch `kubectl get pods -w`
  in another terminal during the same upgrade to see the actual
  interleaving of hook Job pods versus application pod rollout.

## Fix
- Assign explicit `helm.sh/hook-weight` values to every hook that has an
  ordering dependency on another hook of the same type, using clear,
  spaced-out numbers (e.g. `-5`, `0`, `5`) so inserting a new hook later
  doesn't require renumbering everything:

```yaml
metadata:
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation
```

- Use `pre-upgrade` specifically for anything that must complete before
  ANY new manifests are applied (schema migrations that new code
  depends on), and reserve `post-upgrade` for things that only need the
  new manifests to exist, not for things that need new pods to be
  RUNNING and ready -- for the latter (smoke tests against live new
  pods), don't rely on a Helm hook at all; use a separate CI pipeline
  step after `helm upgrade --wait` returns, since `--wait` is what
  actually blocks until the Deployment's new ReplicaSet is ready.
- Set `helm.sh/hook-delete-policy: before-hook-creation` on Job-based
  hooks so a leftover Job from a prior release is cleaned up
  automatically before the next hook Job of the same name is created,
  removing the most common cause of a hook failing with a confusing
  "field is immutable" error that looks like a race condition.
- For a hook that must wait on another resource's actual readiness (not
  just its existence), have the hook's own container perform the
  wait/retry logic (e.g. an init container or entrypoint script polling
  the dependency) rather than assuming Helm's hook-phase ordering
  expresses that dependency.

## Pitfalls
- Setting every hook to the same weight "to be safe" provides no
  ordering guarantee at all and is indistinguishable from setting no
  weight -- weights only establish order relative to OTHER weights present,
  so they must actually differ to have any effect.
- Using `--wait` on `helm upgrade` to make post-upgrade smoke tests
  reliable can significantly increase perceived deploy time and, if
  combined with an aggressive `--timeout`, can cause the upgrade itself
  to be reported as failed even though the application deployed
  successfully and just took longer than expected to reach Ready --
  tune `--timeout` deliberately rather than leaving a default that
  doesn't match the app's real startup profile.

## Verify
Trigger an upgrade that exercises the hook(s) in a test environment,
capture `kubectl get events --sort-by=.lastTimestamp -n <namespace>`
for the full duration of the upgrade, and confirm the hook Job(s)
completed in the intended relative order with the intended relationship
to the Deployment rollout (fully before, for `pre-upgrade`; only after
`--wait` confirms readiness, for anything depending on live new pods).
