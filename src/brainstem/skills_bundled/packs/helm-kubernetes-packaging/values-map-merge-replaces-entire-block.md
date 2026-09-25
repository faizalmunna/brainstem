---
name: values-map-merge-replaces-entire-block
description: An environment-specific values override for one nested key unexpectedly wipes out sibling keys under the same parent map instead of merging alongside them.
triggers: ["helm override values wiped out other keys", "helm -f values file overwrote instead of merging", "helm set only one nested value replaces whole map", "values override deleted unrelated config", "helm merge values list replaced not appended"]
permissions: ["READ"]
---

## Symptom
An environment override file sets a single nested value (e.g.
`resources.limits.cpu` for prod), and after deploying, other sibling
keys under that same parent (e.g. `resources.requests.memory`, which was
only set in the base `values.yaml` and never mentioned in the override)
are missing from the rendered manifest entirely, reverting to the
chart's hardcoded template default (often nothing/empty) rather than the
base value the team expected to still apply.

## Likely causes
1. **The override values file redefines an entire parent map instead of
   only the changed leaf**, e.g. the base `values.yaml` has
   `resources: {limits: {cpu: 500m, memory: 512Mi}, requests: {cpu:
   250m, memory: 256Mi}}` and the override file has only `resources:
   {limits: {cpu: 1000m}}` -- Helm's values merging is a deep merge for
   maps, so this specific case actually *should* merge correctly; the
   more common real trigger is the override accidentally omitting a
   sibling key that was only ever set via `--set` on the command line
   (which doesn't participate in file-based deep merge the same way) or
   via a THIRD values file layered in an unexpected order.
2. **Lists (arrays), not maps, are being partially overridden** -- unlike
   maps, Helm/Go-template YAML merging does NOT deep-merge lists; a
   `-f` override that sets `env:` with two entries completely replaces
   the base's `env:` list of five entries rather than merging or
   appending, because list merge semantics in Helm are whole-value
   replacement, not element-wise merge.
3. **`--set` command-line values interacting with `-f` file values in an
   order that surprises the author** -- `--set` is applied after all
   `-f` files regardless of where it appears in the command, so a
   `--set resources.requests=null`-style override (or an automation tool
   generating `--set` flags) can wipe a whole map if it sets the parent
   key rather than a specific leaf, since setting a map key via `--set`
   without dotted leaf paths for every field replaces the whole subtree.
4. **Multiple `-f` files given in an order where a later file's smaller
   map at the same key path is assumed to merge with an earlier file's
   larger map, but a null or empty value in the later file explicitly
   unsets it** -- Helm treats an explicit `null` in a later-loaded values
   file as "remove this key" during merge, which is a deliberate
   mechanism but is frequently used or hit by accident when a values
   file was templated/generated and produced an empty block instead of
   omitting the key entirely.

## Diagnose
- Run `helm template . -f values.yaml -f values-<env>.yaml
  --show-only <affected-template>` and inspect the exact rendered
  output for the parent map in question, then run `helm template .
  -f values.yaml` alone (base only) and diff -- this isolates whether
  the override file itself is the cause versus a `--set` flag or CI
  automation layered on top in the real deploy command.
- Check whether the affected key is a YAML list (`- item`) or a map
  (`key: value`) in both the base and override files -- list-vs-map is
  the single most useful fact for immediately knowing whether "merge"
  even applies, since Helm never merges list elements.
- Grep the CI/deploy script for every `--set`/`--set-string`/`-f` flag
  used for this release, in the literal order given, and reconstruct the
  full merge manually -- `helm get values <release> -a` on a live
  release shows Helm's own final computed values, which is the
  authoritative answer to "what actually merged," rather than
  reasoning about it from the files alone.
- Search the override values file for an explicit `null` at or above the
  affected key path (`grep -B2 -A2 'null'` or check for an empty `{}` /
  bare key with no value) -- this is the specific YAML shape that
  intentionally deletes a key during merge rather than leaving it
  untouched.

## Fix
- For maps, keep override files scoped to only the exact leaf keys that
  differ -- Helm's default deep-merge behavior for maps already does the
  right thing as long as the override doesn't also accidentally set an
  empty/null value at a higher level than intended; the fix is usually
  correcting the override file's structure/indentation, not fighting
  Helm's merge algorithm.
- For lists, treat any environment override of a list value as a full
  replacement by design -- if the intent is "prod needs the base list
  plus one more entry," the override file must include the complete
  desired list, not just the addition; where charts need genuine
  per-environment list composition, restructure the values schema to use
  a map (keyed by name) instead of a bare list specifically so per-key
  overrides merge correctly, or template the list construction in
  `_helpers.tpl` from separate base/additional-items values keys.
- Standardize on leaf-path `--set` usage (`--set
  resources.limits.cpu=1000m`) rather than `--set
  resources.limits={cpu: 1000m}`-style map-literal sets, and prefer `-f`
  files over `--set` for anything beyond a single scalar override, since
  file-based merging is easier to review and diff than reconstructing
  command-line flag order.
- Audit values-file generation tooling (if values files are templated by
  another script) for accidentally emitting `key: {}` or `key: null`
  instead of omitting a key entirely when there's nothing to override.

## Pitfalls
- "Fixing" a list-replacement surprise by converting a list to a map
  keyed by array index (`"0": {...}, "1": {...}`) technically enables
  per-index override but produces deeply unreadable values files and
  breaks as soon as ordering changes -- prefer a map keyed by a
  meaningful name instead.
- Assuming `helm get values -a` on a live release reflects what the NEXT
  upgrade will compute is only valid if the exact same `-f`/`--set` flags
  are reused -- changing the flag set (even adding one more `-f` file)
  changes the merge result independent of what's currently live.

## Verify
Run `helm get values <release> -a -o yaml` after deploying and manually
confirm every expected sibling key under the affected parent map is
present with the expected value (both the ones explicitly overridden and
the ones expected to fall through from the base) -- do not infer
correctness from the override file alone, since only Helm's own computed
merge output reflects reality.
