---
name: sveltekit-route-params-component-not-updating
description: Diagnose a SvelteKit page component that keeps showing stale content when navigating between routes sharing the same dynamic segment.
triggers: ["component not remounting sveltekit", "route params not updating component", "onmount not firing on navigation", "same page different slug not updating", "sveltekit navigation stale component state"]
permissions: ["READ"]
---

## Symptom
Navigating from `/products/1` to `/products/2` (a route matched by the
same `[id]` dynamic segment) updates the URL and the `params`/`data`
props, but visible component state built from the *old* params -- a
locally initialized `$state` variable, an imperative third-party widget,
a scroll position -- doesn't reset, because SvelteKit reuses the existing
component instance instead of destroying and recreating it.

## Likely causes
1. **`onMount` logic that reads route params only runs once per component
   instance's lifetime**, and SvelteKit deliberately keeps the same
   instance alive across navigations within the same route component,
   for performance -- code that expected "remount on every navigation"
   never reruns.
2. **A local `$state` variable is seeded from a prop at declaration time**
   (`let selected = $state(data.item)`), which only captures `data.item`'s
   value the instant the component was first created -- subsequent
   navigations update the `data` prop, but the `$state` initializer
   doesn't rerun, so `selected` keeps the original value.
3. **A third-party library or DOM widget was initialized imperatively in
   `onMount`** (a map, a chart, an editor) keyed to the old params, and
   nothing tells it to reinitialize when the params change, since the
   component itself never remounts.
4. **`$page.params` (or the load `params`) is read into a plain
   non-reactive variable at the top of the script** instead of being
   referenced reactively (directly, or via `$derived`), so later changes
   to params after navigation don't propagate to anything computed from
   that captured copy.

## Diagnose
- Confirm reuse is actually happening: add a `console.log('component
  created')` at the top-level script (runs once per instance) versus a
  `$effect(() => console.log('params changed', page.params.id))` --
  if the first logs once across two navigations and the second logs
  twice, the component is being reused (expected), and code needs to
  react to the second, not rely on the first.
- Grep for `$state(data.xxx)` or `$state(params.xxx)` patterns --
  these are classic "seeded once" bugs when the surrounding component
  persists across navigations.
- Check whether imperative third-party initialization lives in `onMount`
  with no corresponding `$effect` or `afterNavigate` hook to reinitialize
  it on subsequent param changes.
- Use SvelteKit's `afterNavigate` (from `$app/navigation`) with a log to
  confirm it fires on every navigation, including ones that reuse the
  component -- unlike `onMount`, this hook is exactly the "did navigation
  happen" signal that's needed here.

## Fix
- Replace a one-time `$state(data.item)` seed with a `$derived(data.item)`
  when the value should simply always mirror the current prop, or use an
  `$effect` that explicitly resyncs local state whenever `data`/`params`
  changes, if the local state needs to be independently mutable but reset
  on navigation.
- For imperative widgets, initialize/reinitialize them inside an
  `$effect` that reads the params it depends on, so it reruns its cleanup
  and setup logic whenever those specific values change -- this replaces
  the "runs once in onMount" assumption with the correct "runs whenever
  its dependencies change" behavior.
- If a full remount is genuinely the right model for a specific subtree
  (e.g. a complex uncontrolled widget with no clean update API), wrap
  just that subtree in `{#key params.id}...{/key}` to force Svelte to
  destroy and recreate it on param changes, rather than fighting the
  default instance-reuse behavior for the whole page.
- Read `page.params`/`data` reactively wherever used (directly in the
  template, or through `$derived`), not copied into a plain variable at
  the top of the script.

## Pitfalls
- Wrapping the entire page in `{#key $page.url.pathname}` to force a
  remount on every navigation throws away the performance benefit
  instance-reuse provides and can reintroduce layout flicker/scroll
  jumps -- scope `{#key}` to the smallest subtree that actually needs to
  reset.
- Moving everything into `$effect` blocks indiscriminately "just in case"
  can turn a simple param-driven resync into a tangle of effects that
  re-trigger each other -- keep each effect scoped to one clear
  responsibility (usually: reinitialize this one thing when this one
  value changes).

## Verify
Navigate between two routes sharing the same dynamic segment and confirm
the previously-stale state (displayed value, widget content, or whatever
was affected) updates to match the new params without a full page reload,
while checking that navigating away and back doesn't cause unnecessary
extra work (e.g. duplicate widget instances) from over-applying `{#key}`.
