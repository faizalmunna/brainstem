---
name: sveltekit-form-action-data-not-updating-page
description: Diagnose a SvelteKit form action whose returned data or validation errors don't appear on the page without a manual browser reload.
triggers: ["form action not updating page", "use:enhance not updating", "sveltekit form data stale", "action result not showing", "form prop not updating svelte"]
permissions: ["READ"]
---

## Symptom
Submitting a `<form method="POST" action="?/save">` runs the server
action successfully (confirmed in server logs or the Network tab), but
the page doesn't reflect the result -- the `form` prop stays empty,
validation errors don't render, or a list that the action just modified
still shows old data -- until the user manually refreshes the browser.

## Likely causes
1. **A custom `use:enhance` callback that doesn't call `update()` (or
   `applyAction()`).** By default, `use:enhance` applies the action's
   result to the page automatically. As soon as you pass a callback to
   customize behavior (e.g. to show a toast), that callback replaces the
   default application logic -- if it doesn't explicitly call the
   `update` function it's given, the result is fetched but never applied
   to `form`/`page.data`.
2. **The form has no `use:enhance` at all.** Without it, the browser does
   a real, full-document POST navigation. This isn't "broken" -- the page
   genuinely does update, but only via a full reload, which is exactly the
   reported symptom if the expectation was an SPA-style update.
3. **The action succeeds but the page's `load` function isn't rerun.**
   SvelteKit's default `use:enhance` behavior calls `invalidateAll()`
   after a successful, non-redirecting action response -- but a custom
   callback that calls `update({ reset: false })` without also invoking
   `invalidateAll` (when it overrides default behavior) will refresh the
   `form` prop but leave any *other* page data (e.g. a list fetched in
   `load`) stale.
4. **Non-serializable data returned from the action** (a `Date`, a class
   instance, a `Map`) gets silently stripped or converted unexpectedly by
   SvelteKit's `devalue`-based serialization, so parts of `form` are
   `undefined` even though the server clearly set them.
5. **The component reads the prop the old way** (`export let form` left
   over from a Svelte 4 file, or a stale destructure that isn't rebound to
   `$props()`), so updates to the underlying prop never reach the local
   binding used in the template.

## Diagnose
- Confirm whether `use:enhance` is present on the `<form>` at all --
  without it, the "doesn't update without reload" symptom is expected
  behavior (a real navigation is happening), not a bug.
- If `use:enhance` has a callback argument, check whether the callback's
  returned function actually calls the `update` argument it receives --
  a callback that only does `if (result.type === 'success') showToast()`
  and returns nothing has silently opted out of applying the result.
- Log the raw action return value on the server and compare it to what
  `form` contains in the component -- a mismatch (fields missing or
  `undefined`) points at serialization (cause 4) rather than a wiring bug.
- Check whether the page's own `load` function needs to rerun for the
  visible discrepancy (e.g. a list) versus just the `form` prop for
  inline validation -- these are two different data paths.

## Fix
- In a custom `use:enhance` callback, always call the provided `update()`
  function (optionally with options like `{ reset: false }`) unless
  there's a specific reason to suppress it -- this restores the default
  "apply the result to `form` and rerun invalidated loads" behavior while
  still letting the callback add custom side effects like toasts.
- If other page data (not just `form`) needs to refresh after the action,
  either let the default `invalidateAll()` behavior run (don't suppress
  it in the callback) or call `invalidateAll()`/`invalidate(key)`
  explicitly inside the callback for the specific data affected.
- Return only serializable data from actions (plain objects, arrays,
  primitives, or values `devalue` explicitly supports) -- convert
  `Date`s to ISO strings and class instances to plain objects before
  returning them from `fail()` or the action's return value.
- Make sure the component uses `let { form } = $props()` (runes mode) or
  the equivalent current binding style consistently, not a leftover
  `export let form` mixed with rune-based state elsewhere in the same
  file.

## Pitfalls
- Calling `invalidateAll()` unconditionally inside every `use:enhance`
  callback "to be safe" causes the over-refetching problem described in
  the load-rerunning-unexpectedly skill -- scope invalidation to what the
  action actually changed.
- Wrapping the whole form in manual `fetch()` calls to bypass SvelteKit's
  form handling (in order to "fix" the update issue) throws away
  progressive enhancement, CSRF protections, and automatic serialization
  that `use:enhance` provides for free -- fix the callback instead of
  replacing the mechanism.

## Verify
Submit the form with JavaScript enabled and the Network tab open; confirm
the request is a `fetch` (not a full navigation), that the response's
data appears in the UI immediately without a manual reload, and that
disabling JavaScript still results in a correct (if slower, full-reload)
outcome via the same action.
