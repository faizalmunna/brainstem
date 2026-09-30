---
name: svelte5-snippet-not-reactive-to-parent-state
description: Diagnose a Svelte 5 snippet passed to a child component that stops reflecting subsequent changes to the state it closes over.
triggers: ["snippet not reactive svelte", "@render not updating", "snippet stale value svelte 5", "children snippet not updating", "svelte snippet closure stale"]
permissions: ["READ"]
---

## Symptom
A parent passes a `{#snippet ...}` (including the implicit `children`
snippet from default slot content) to a child component, the child
renders it with `{@render someSnippet()}`, and it displays correctly on
first render -- but subsequent changes to the parent state the snippet's
body reads don't show up, even though the same state updates other parts
of the parent's own template fine.

## Likely causes
1. **The child captures the *result* of calling the snippet once instead
   of invoking it at render time.** A snippet is a function meant to be
   called via `{@render snippet()}` directly in the template on every
   render pass; code that does `const rendered = someSnippet()` once
   (e.g. in a `$derived` or at initialization) and reuses that captured
   result freezes it at that instant, since the *call* -- not the
   snippet's continued existence -- is what re-executes its reactive
   reads.
2. **The snippet reference itself is copied into local `$state` at
   mount** (`let snap = $state(children)`) under the mistaken assumption
   that this "memoizes" it for performance -- this disconnects the local
   binding from the live prop, so if the parent ever passes a genuinely
   new snippet (not just the same one), the child never picks it up.
3. **The snippet is invoked conditionally behind a flag that's only ever
   set once** (`{#if mounted}{@render snippet()}{/if}` where `mounted`
   flips `true` in `onMount` and never changes again) -- this isn't a
   reactivity bug in the snippet itself, but it looks identical from the
   outside: the snippet's *first* invocation's output stops updating
   because the surrounding block never re-executes the render call for
   reasons unrelated to the snippet.
4. **A value is captured by-reference in an `{#each}` loop that generates
   snippet call sites**, where the loop variable is reused/stale by the
   time the snippet actually renders asynchronously (e.g. inside a
   `Promise.then` or `setTimeout` scheduled from within the snippet body)
   -- a closure-over-loop-variable bug that happens to surface via a
   snippet rather than being specific to snippets.

## Diagnose
- Find every call site of the snippet (`{@render name(...)}`) and confirm
  it's written directly in the template (or inside a reactive block like
  `{#if}`/`{#each}` that itself re-renders), not assigned to a variable
  and reused.
- Grep for the snippet's name preceded by `const`/`let` followed later by
  reuse of that variable instead of a fresh `{@render}` call -- this is
  the single most common form of the bug.
- Check whether the snippet (or `children`) was ever wrapped in `$state()`
  or `$derived()` locally in the child -- snippets don't need to be
  wrapped in a rune to stay reactive; wrapping them is usually the bug,
  not the fix.
- For the conditional-gate case, log the guarding boolean/condition right
  next to the `{@render}` call and confirm it's actually re-evaluating on
  the updates in question, as opposed to having latched `true` once.

## Fix
- Always invoke the snippet directly where it's rendered
  (`{@render children()}`) rather than storing its return value --
  `{@render}` re-executes the snippet's body (and therefore re-reads
  whatever reactive state it closes over) on every render pass the
  surrounding markup goes through, which is the entire point of the
  snippet/render split versus old static slot content.
- Reference the snippet prop directly from `$props()` without copying it
  into local `$state` -- if the parent passes a new snippet instance,
  the live prop binding already reflects that on the next render; local
  state only adds a stale copy.
- Remove render-gating conditions that are set once and never revisited
  if the actual intent was "always show this, once available" -- use a
  condition that continues to reflect current reality (e.g. `{#if
  data}...{/if}` with `data` itself reactive) rather than a one-shot
  `mounted` flag.
- For loop-scoped snippet closures, pass the current loop value as an
  explicit snippet parameter (`{#snippet row(item)}...{/snippet}` /
  `{@render row(currentItem)}`) instead of relying on outer closure
  capture across an async boundary.

## Pitfalls
- Wrapping the snippet call's output in `$derived.by` to "cache" it for
  performance defeats the render-time invocation model snippets are
  built on and reintroduces exactly the staleness this skill diagnoses --
  snippets are already cheap to invoke; don't memoize the call.
- Converting a snippet back to a legacy `<slot>` as a workaround changes
  the composition model for every consumer of the component, not just
  the one broken call site, and loses the ability to pass parameters into
  the rendered content that snippets support.

## Verify
Change the parent state the snippet body reads, and confirm the rendered
output inside the child updates immediately on the next render without
any remount -- then confirm the fix didn't regress the initial render (the
snippet should still show correctly-initialized content the first time
too).
