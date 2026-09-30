---
name: helm-upgrade-succeeds-but-pods-run-stale-config
description: A helm upgrade reports success and the release revision increments, but running pods keep executing with the previous ConfigMap or Secret contents.
triggers: ["helm upgrade succeeded but old config still running", "configmap change not applied after helm upgrade", "pods not picking up new values after helm upgrade", "helm release updated but app behaves like before"]
permissions: ["READ"]
---

## Symptom
`helm upgrade` exits 0, `helm history` shows a new revision deployed, and
`helm get values` shows the new values -- but the actual running pods are
still behaving as if nothing changed. Exec'ing into a pod (or checking its
mounted config) shows the OLD ConfigMap/Secret content, or the app's
in-memory config clearly hasn't changed, even though `kubectl get
configmap -o yaml` shows the new content on the cluster.

## Likely causes
1. **No checksum/hash annotation on the pod template referencing the
   ConfigMap/Secret content.** Helm renders a new ConfigMap object and
   applies it, but if the Deployment's pod template spec is byte-for-byte
   identical to before (which it is, if the only change was inside the
   ConfigMap and the Deployment just references it by name), Kubernetes
   sees no diff on the Deployment/pod template and never triggers a
   rollout -- only the standalone ConfigMap object gets updated in place.
2. **ConfigMap/Secret consumed as environment variables**, which are
   fixed at container start regardless of any annotation -- even with a
   correct checksum annotation forcing a new pod, this is a separate but
   related trap if someone assumes env vars behave like mounted files.
3. **Immutable ConfigMap/Secret with a static name**, where the chart
   was changed to use `immutable: true` (or a values flag intended to
   enable content-hash-suffixed names) but the resource name is still
   static -- the apply either fails silently in a pruned way or the old
   object is left bound to the old ReplicaSet with no forced rollout.
4. **A `helm upgrade` running with `--no-hooks` or against a values file
   that didn't actually change the rendered ConfigMap** -- e.g. the
   environment variable/values path being edited doesn't map to the key
   actually referenced in `configmap.yaml`'s template, so the rendered
   ConfigMap content is identical to before and there was never a
   change to propagate.

## Diagnose
- Run `helm get manifest <release> | grep -A5 'kind: Deployment'` and
  check whether `spec.template.metadata.annotations` contains any
  checksum-style key (e.g. `checksum/config`). If it's absent, that's
  the primary cause.
- Compare `kubectl get configmap <name> -o yaml` (live cluster content)
  against `helm get manifest <release> | grep -A50 'kind: ConfigMap'`
  (what Helm last rendered) -- if they match but the pod's mounted file
  or env still shows old values, the ConfigMap updated but the pod
  never restarted.
- Run `kubectl rollout history deployment/<name>` and `kubectl describe
  deployment/<name> | grep -A5 'RollingUpdateStrategy\|OldReplicaSets'`
  -- if no new ReplicaSet was created at the time of the `helm upgrade`,
  the Deployment's pod template genuinely didn't change.
- Diff the rendered ConfigMap before and after the values change with
  `helm template . -f old-values.yaml` vs `helm template . -f
  new-values.yaml` to confirm the value change actually reaches the
  ConfigMap template at all (rule out a values-path/key mismatch).

## Fix
Add a checksum annotation to the pod template that hashes the rendered
ConfigMap/Secret content, so any content change necessarily changes the
Deployment's pod template and forces a real rollout:

```yaml
spec:
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        checksum/secret: {{ include (print $.Template.BasePath "/secret.yaml") . | sha256sum }}
```

This works because Helm evaluates the annotation value at render time by
re-rendering the referenced template partial and hashing its output --
any change to the ConfigMap/Secret template or the values feeding it
changes the hash, which changes the pod template, which Kubernetes
recognizes as a spec change requiring a new ReplicaSet. For charts where
hand-rolling this on every resource is error-prone, use a community
helper (e.g. the `reloader` controller pattern, annotating resources with
`configmap.reloader.stakater.com/reload`) as an alternative that reloads
based on a controller watching ConfigMaps rather than a template-time
hash.

## Pitfalls
- Hashing the entire values file (`{{ .Values | toYaml | sha256sum }}`)
  instead of just the specific template partial causes pods to restart on
  every single upgrade, even ones touching unrelated values -- this
  defeats the purpose of rolling updates being scoped to actual changes
  and creates unnecessary churn/downtime risk on unrelated releases.
- Adding the checksum annotation only to newly-written charts and
  forgetting existing charts already in production means old releases
  keep silently failing to roll on config change until someone notices
  behavior didn't change after a values update.

## Verify
Change a value that feeds the ConfigMap, run `helm upgrade`, then
immediately run `kubectl rollout status deployment/<name>` and confirm
it reports a new rollout in progress (not "already up to date"), and
`kubectl get pods -o jsonpath='{.items[*].metadata.creationTimestamp}'`
shows fresh pod creation timestamps after the upgrade completed.
