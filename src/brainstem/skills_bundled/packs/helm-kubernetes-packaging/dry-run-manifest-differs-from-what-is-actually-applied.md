---
name: dry-run-manifest-differs-from-what-is-actually-applied
description: The manifest shown by helm template or helm install --dry-run looks correct, but the object actually running on the cluster differs from it after real deployment.
triggers: ["helm dry-run looks fine but deployed differently", "helm template output does not match live cluster resource", "admission webhook changed my helm deployment", "post-render hook changing manifest after helm install", "kubectl get shows different spec than helm template"]
permissions: ["READ"]
---

## Symptom
`helm template` or `helm install/upgrade --dry-run` produces a manifest
that looks exactly right -- correct image tag, correct resource limits,
correct labels -- but after the real (non-dry-run) install/upgrade,
`kubectl get <resource> -o yaml` shows a materially different spec:
extra sidecar containers, mutated labels/annotations, a different
resource request, or an injected field nobody's chart template
authored.

## Likely causes
1. **A Kubernetes admission webhook (mutating webhook) modifies the
   object after it's submitted to the API server** -- Helm's dry-run
   modes (client-side `helm template`, or `--dry-run=client`) never
   contact the API server at all, so they cannot reflect anything a
   mutating webhook would do (e.g. Istio/service-mesh sidecar injection,
   an OPA/Gatekeeper mutation, a PodSecurity mutation, a cloud provider's
   own injected annotations); even `--dry-run=server` only shows the
   result of validating/mutating webhooks IF the dry-run request itself
   passes through them, which depends on webhook configuration.
2. **A configured Helm post-render hook or `--post-renderer` binary**
   (e.g. Kustomize-based post-processing, a company-standard patcher)
   transforms the manifest after Helm renders it but before it's applied
   -- `helm template` without also invoking the same post-renderer shows
   pre-transform output, which is a different artifact than what
   actually reaches `kubectl apply`.
3. **Server-side apply / strategic merge with an existing object**
   introduces fields from the previous live object's state that the new
   manifest doesn't explicitly override or remove -- a field set by a
   previous release (or by something else entirely, like an HPA writing
   back `replicas`) can persist through an upgrade if the new template
   doesn't explicitly manage that field, making the live object a merge
   of old-and-new rather than a clean replacement matching the rendered
   manifest.
4. **Cluster-level defaulting from the API server or a `LimitRange`/
   `ResourcePolicy` admission controller** fills in fields the chart
   left unset (default resource requests, a default storage class) --
   these appear on the live object but were never in the rendered
   manifest because Helm only renders what the chart explicitly
   specifies.

## Diagnose
- Check for a post-renderer: `helm get metadata <release>` and the
  actual `helm upgrade`/`install` command used in CI (`grep -r
  "post-renderer" .ci/ Makefile`) -- if one is configured, `helm
  template` alone is provably not equivalent to what was deployed, and
  the post-renderer must be invoked identically to reproduce the real
  output (`helm template . | <post-renderer-binary>`).
- List mutating webhook configurations that could plausibly touch the
  resource: `kubectl get mutatingwebhookconfigurations` and inspect each
  one's `rules`/`namespaceSelector` for whether it matches this
  resource's kind and namespace.
- Compare `helm get manifest <release>` (what Helm actually submitted,
  post-render, pre-admission) against `kubectl get <resource> -o yaml`
  (live, post-admission) -- fields present in the live object but absent
  from `helm get manifest` were added by something outside Helm's own
  rendering, narrowing it to admission-time mutation or API-server
  defaulting.
- For suspected HPA/controller write-back on `replicas` or similar,
  check `kubectl get <resource> -o yaml` across two points in time with
  no Helm operation in between -- if the field changes on its own, a
  controller (not Helm, not admission) owns that field and any diff
  against the chart's static value is expected, not a bug.

## Fix
- Always reproduce dry-run output through the exact same pipeline used
  for real deploys, including any post-renderer: treat `helm template .
  | <post-renderer>` (or `helm template . --post-renderer
  <path>`) as the actual "what will be applied" preview, not bare `helm
  template` alone, and document this as the team's standard preview
  command.
- For resources subject to known mutating webhooks (service mesh
  sidecar injection being the most common), don't try to make Helm's
  static output match post-mutation state -- instead, verify against the
  live object after a real (or `--dry-run=server`, when the webhook is
  configured to apply to dry-run requests) apply, and treat the
  webhook's contribution as a separate, intentionally-owned layer rather
  than something the chart should attempt to replicate.
- For fields another controller legitimately owns after initial creation
  (HPA-managed `replicas`, an operator-managed status-derived field),
  either omit them from the chart's template entirely (let the
  controller own creation-time defaults too) or use `kubectl` apply
  strategies / Helm's `.Values` explicitly documented as "initial value
  only, not enforced," so nobody mistakes chart drift for a bug when the
  controller is working as intended.
- When cluster-level defaulting (LimitRange, default StorageClass) is
  filling in values, make the chart set them explicitly if the specific
  value matters, rather than relying on cluster defaults that can differ
  between environments/clusters running the same chart.

## Pitfalls
- Adding a post-renderer to "fix" a webhook mutation by pre-emptively
  patching the manifest to match the post-mutation state creates a
  fragile coupling where a webhook config change now requires a chart
  change to stay in sync, instead of letting the webhook do its job
  independently of the chart.
- Assuming any live/rendered diff must be an admission webhook without
  checking for a post-renderer first wastes time auditing cluster-wide
  webhook configs for a problem that's actually a one-line, chart-repo
  -local `--post-renderer` flag.

## Verify
Run the team's full deploy-preview command (including any post-renderer)
and diff its output against `helm get manifest <release>` immediately
after a real deploy -- they should match exactly for every field Helm
itself is responsible for; any remaining diff should be traceable to a
specific, named mutating webhook or controller, not left as an
unexplained discrepancy.
