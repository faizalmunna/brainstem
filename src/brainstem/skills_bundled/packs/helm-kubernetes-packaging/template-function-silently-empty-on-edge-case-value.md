---
name: template-function-silently-empty-on-edge-case-value
description: A chart template renders as blank, zero, or subtly wrong for an edge-case value like an empty list or missing map key instead of raising an error.
triggers: ["helm template renders empty for missing value", "helm range produces nothing", "helm chart wrong output empty list", "helm template silently wrong not failing", "go template missing key no error"]
permissions: ["READ"]
---

## Symptom
`helm template`/`helm install` completes without error, but the rendered
manifest is missing an expected block entirely (a `range` over a list
produced zero iterations), or a field renders as an empty string, `0`, or
`<no value>` instead of the intended value -- and crucially, nothing
failed loudly, so this often ships to production and is only noticed when
the resulting resource misbehaves (e.g. a Service with no ports, an
Ingress with no rules, a container with an empty image tag).

## Likely causes
1. **`range` over a nil or absent list produces zero output with no
   error** -- Go templates treat ranging over `nil` the same as ranging
   over an empty slice; if `.Values.ingress.hosts` was never set (as
   opposed to set to `[]`), a template author who only tested with the
   list populated never sees that the `range` block silently emits
   nothing rather than failing.
2. **Dotted/nested key access on a missing intermediate map returns an
   empty value instead of erroring**, because Go templates' default
   behavior for a missing map key is to substitute the zero value (empty
   string, `0`, `false`) rather than raise an error -- `{{
   .Values.resources.limits.cpu }}` renders as empty if `resources` was
   omitted from an override file entirely, rather than failing at
   render time.
3. **`default` used incorrectly to mask exactly this problem** -- a
   template with `{{ .Values.replicas | default 1 }}` looks like
   defensive coding, but `default` in Sprig only substitutes on Go's
   notion of "empty" (nil, "", 0, false), so a deliberately-set `0` (a
   legitimate value for e.g. `minReplicas` in some contexts) gets
   silently overridden to the fallback, producing wrong-not-missing
   output.
4. **`toYaml`/`nindent` on an empty or nil value produces valid-looking
   but semantically empty YAML** -- `{{- with .Values.annotations }}{{
   toYaml . | nindent 4 }}{{- end }}` on an unset `annotations` value
   just omits the block cleanly, which is often fine, but the same
   pattern used for a required field (e.g. `selector`) produces a
   Kubernetes object that is schema-valid but functionally broken (a
   Service matching everything or nothing).

## Diagnose
- Run `helm template . --debug` and inspect the exact rendered output
  around the suspect block -- look specifically for an empty block where
  content was expected, `<no value>`, or a value of `0`/`false`/`""`
  that doesn't match what the values file appears to specify.
- Temporarily add `{{ required "X must be set" .Values.x }}` around the
  suspected value in a scratch copy of the template and re-render -- if
  it now errors, the value was genuinely missing/nil and previously
  failing silently; if it still renders fine, the bug is elsewhere in
  the template logic.
- Grep the chart's templates for `range`, `default`, and bare `.Values.`
  dotted-path access without `required` or an explicit nil-check, and
  cross-reference each against whether the corresponding values key is
  guaranteed to be set by the schema or every values file in use.
- Run `helm lint` and `helm template . -f values.yaml -f
  values-<env>.yaml --strict` for every real environment's values
  combination, not just the default values.yaml, since the edge case
  usually only manifests with a specific environment's incomplete
  override.

## Fix
Make missing-value cases fail loudly at render time instead of
succeeding with wrong output, using the tools built for exactly this:
- Wrap genuinely required values in `required`: `{{ required
  "ingress.hosts must be set" .Values.ingress.hosts }}` so an absent or
  nil value stops the render with a clear message naming the missing
  key, instead of producing an empty Ingress.
- For lists that are optional but should behave predictably when absent,
  make the "empty" case explicit and intentional with `{{- if
  .Values.ingress.hosts }}...{{- else }}{{- fail "at least one ingress
  host is required" }}{{- end }}` when emptiness is actually invalid, or
  document/comment the template clearly when an empty list intentionally
  means "render nothing here."
- Replace `default` on values where `0`/`false` is a legitimate,
  meaningful setting with an explicit nil-check: `{{- if hasKey .Values
  "replicas" }}{{ .Values.replicas }}{{- else }}1{{- end }}`, since
  `hasKey` distinguishes "key present with a falsy value" from "key
  absent" where `default` cannot.
- Back required values with a `values.schema.json` `required` array so
  the failure surfaces even earlier, at `helm lint`/schema-validation
  time, before template rendering is reached at all.

## Pitfalls
- Wrapping every single `.Values.x` access in `required` makes the chart
  brittle for legitimately optional fields and forces every consumer to
  set values they don't need to care about -- reserve `required` for
  values with no sane default where proceeding would produce a broken
  resource, not as a blanket habit.
- Fixing a `default`-on-falsy-value bug by simply removing `default`
  without adding a `hasKey` check trades a silent-wrong-value bug for a
  silent-empty-value bug -- the fix must explicitly handle the
  "key absent" branch, not just stop masking it.

## Verify
Render the chart against a values file that deliberately omits the field
in question (`helm template . -f values-missing-field-test.yaml`) and
confirm it either fails with the specific `required`/`fail` message
naming that field, or renders the explicitly-documented fallback
behavior -- not an empty block or a `<no value>` that would previously
have gone unnoticed.
