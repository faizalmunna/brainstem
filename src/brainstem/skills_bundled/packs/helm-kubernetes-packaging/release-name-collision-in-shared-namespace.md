---
name: release-name-collision-in-shared-namespace
description: Installing the same chart a second time in one namespace overwrites or collides with resources from the first release because names are not release-scoped.
triggers: ["helm install second release overwrote first", "resource already exists owned by another release", "helm chart name collision same namespace", "multiple helm releases same namespace conflict", "cannot reuse a name that is still in use helm"]
permissions: ["READ"]
---

## Symptom
Installing the same chart twice in one namespace with two different
release names (e.g. `helm install team-a ./chart` and `helm install
team-b ./chart` in the same namespace) either fails outright with
`rendered manifests contain a resource that already exists... cannot
patch/create resource, another resource with the same name but different
owner already exists`, or -- worse -- silently succeeds by having the
second install overwrite/adopt a resource the first release created,
causing the first release's Deployment or Service to be reconfigured out
from under it.

## Likely causes
1. **Templates hardcode a resource name instead of deriving it from
   `.Release.Name`** -- a template with `name: my-app-service` (a
   literal string) or `name: {{ .Chart.Name }}-service` (derived only
   from the chart, which is identical across every release of that
   chart) produces the exact same resource name regardless of which
   release installed it, so two releases of the same chart in the same
   namespace inevitably try to own the same object.
2. **`fullname` helper template not actually used consistently** -- most
   scaffolded charts include a `{{ include "<chart>.fullname" . }}`
   helper specifically designed to incorporate `.Release.Name` (via the
   standard `_helpers.tpl` pattern from `helm create`), but individual
   resource templates added later by hand reference a hardcoded name or
   `{{ .Chart.Name }}` directly instead of calling the helper, bypassing
   the protection that already exists elsewhere in the same chart.
3. **Cluster-scoped or otherwise inherently-unique-required resources**
   (a `ClusterRole`, a `StorageClass`, a webhook configuration name) that
   the chart author didn't realize need release-scoping because most of
   the chart's resources are namespaced and correctly scoped, but this
   one cross-cutting resource was written assuming single-install-per-
   cluster use.
4. **Two releases intentionally sharing one underlying resource on
   purpose** (e.g. both should point at one shared ConfigMap or
   ServiceAccount) but without Helm's ownership model accounting for
   shared resources -- Helm's default model assumes one release owns
   each resource it creates, so intentional sharing needs an explicit
   pattern (a resource created outside Helm's management, or one release
   designated as the owner with others referencing it read-only), not
   just "both charts happen to compute the same name."

## Diagnose
- Run `helm template <release-name> ./chart` for two different candidate
  release names and diff the two outputs' `metadata.name` fields across
  every resource -- any resource name that's identical between the two
  renders will collide if both are installed in the same namespace.
- Grep chart templates for `name:` lines and check whether each one uses
  `{{ include "<chart>.fullname" . }}` (or equivalent release-scoped
  helper) versus a literal string or `{{ .Chart.Name }}` alone -- the
  latter two are namespace-collision-prone by construction.
- If a collision already occurred, run `kubectl get <resource> -o
  jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}'` to see
  which release Helm currently believes owns the contested resource, and
  compare against `helm list -n <namespace>` to see both releases'
  actual state (one may now show as failed/superseded).
- Check `_helpers.tpl` for the presence and correctness of the standard
  `fullname` helper (`{{- define "<chart>.fullname" -}}` block using
  `.Release.Name`) to confirm the safety net exists at all versus having
  been removed or never generated (e.g. a chart not originally scaffolded
  via `helm create`).

## Fix
Ensure every namespaced resource's name is derived through a single
release-scoped helper, and use it everywhere without exception:

```yaml
# _helpers.tpl
{{- define "mychart.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
```

```yaml
# every resource template
metadata:
  name: {{ include "mychart.fullname" . }}
```

This works because `.Release.Name` is unique per Helm install by
Helm's own enforcement (`helm install` refuses two releases with the
identical name in the identical namespace already), so deriving every
resource name from it transitively guarantees uniqueness across
releases without the chart author needing to reason about it
per-resource. For inherently cluster-scoped resources that legitimately
need to be singleton, name them explicitly and document that the chart
is only safe to install once per cluster for that resource type,
rather than pretending release-scoping solves an intentionally-shared
resource.

## Pitfalls
- Truncating the release-name-derived string without `trunc 63` (the
  Kubernetes object name length limit) causes a *different* failure mode
  that only appears with long release names, which can look unrelated to
  the collision problem but stems from the same helper -- always include
  the length guard.
- Fixing the hardcoded-name templates but leaving already-deployed
  colliding resources in place means the fix only prevents *future*
  collisions; existing installations still share the old resource and
  need a coordinated migration (rename via a new install + old release
  uninstall, planned as a change with downtime/traffic implications, not
  a silent template fix).

## Verify
Install the chart twice under two different release names into the same
namespace in a scratch/test cluster (`helm install rel-a ./chart -n
test-ns` then `helm install rel-b ./chart -n test-ns`) and confirm both
succeed with `helm list -n test-ns` showing both as `deployed`, and
`kubectl get all -n test-ns` showing two full, distinctly-named sets of
resources with no ownership conflicts reported by either install.
