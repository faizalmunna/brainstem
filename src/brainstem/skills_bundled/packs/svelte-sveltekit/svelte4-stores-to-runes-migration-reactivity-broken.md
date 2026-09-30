---
name: svelte4-stores-to-runes-migration-reactivity-broken
description: Diagnose reactivity that silently breaks after migrating a Svelte 4 component from stores and reactive statements to Svelte 5 runes.
triggers: ["reactivity broke after svelte 5 migration", "$: not working svelte 5", "converted to runes stopped updating", "svelte 5 migration reactive statement", "runes migration state not updating"]
permissions: ["READ"]
---

## Symptom
After converting a component (or a shared module) from Svelte 4 idioms --
`export let prop`, `$: computed = ...`, `writable()` stores -- to Svelte 5
runes, some value that used to update automatically now only computes
once, or a value shared across modules stops propagating changes to
importers.

## Likely causes
1. **A `$: computed = expr` reactive statement was replaced with a plain
   `let computed = expr` instead of `let computed = $derived(expr)`.**
   Without `$derived` (or the old `$:`), the right-hand side is evaluated
   exactly once, at declaration time -- there's no mechanism left to
   rerun it when its inputs change.
2. **Runes were used in a plain `.js`/`.ts` file.** `$state`, `$derived`,
   and `$effect` only work inside `.svelte` files or files with the
   `.svelte.js`/`.svelte.ts` extension, which the Svelte compiler treats
   specially. Renaming a shared "store" module to plain `.js` during
   migration silently breaks (or outright errors on) any rune usage in
   it.
3. **A rune-based value is exported directly from a module and
   reassigned from a different module.** `export let count = $state(0)`
   from a `.svelte.js` file lets other modules *read* and see live
   updates to `count`'s properties, but a plain top-level `let` binding
   can't be reassigned from outside its own module in JavaScript --
   attempting `count = 5` from an importer either errors or silently does
   nothing useful, unlike a Svelte 4 `writable` store's `.set()`.
4. **Old and new patterns are mixed inconsistently** -- e.g. still using
   `export let prop` for some props while others were converted to
   `$props()`, or keeping a `$store` auto-subscription on a variable that
   was actually converted to a rune (which isn't a store and has no
   `subscribe` method, so `$` prefix access throws or is meaningless).
5. **A two-way bound prop wasn't converted to `$bindable()`.** A prop
   that a parent binds to with `bind:value` needs the child to declare it
   via `let { value = $bindable() } = $props()` -- leaving it as a plain
   `$props()` destructure without `$bindable` makes writes from the child
   silently fail to propagate back to the parent.

## Diagnose
- Grep the migrated file for any `let x = ` followed by an expression that
  references other reactive variables, without `$derived`/`$derived.by`
  wrapping it -- these are prime candidates for "used to be `$:`, now just
  runs once."
- Check the file extension of any module exporting shared reactive state:
  is it `.js`/`.ts`, or `.svelte.js`/`.svelte.ts`? Runes in the former
  either throw a compiler error or (depending on tooling) fail silently.
- For cross-module state, check whether consumers try to reassign an
  imported binding directly (`import { count } from './state.svelte.js';
  count = 5`) rather than calling a setter or mutating an object's
  property.
- Grep for `$` -prefixed variable usage (`$myStore`) next to a declaration
  that was changed to `$state(...)` -- mixing the two syntaxes on the same
  name is a strong signal of an incomplete migration.
- Check every `bind:` usage on custom components against the child's
  prop declaration for a matching `$bindable()`.

## Fix
- Convert every `$: computed = expr` to `let computed = $derived(expr)`
  (or `$derived.by(() => {...})` for multi-statement logic) rather than a
  bare `let` -- this is the direct rune equivalent, not an optional
  upgrade.
- Rename any module that declares runes at the top level to
  `.svelte.js`/`.svelte.ts` so the compiler processes it correctly.
- For cross-module shared state, export either an object with a mutable
  property (`export const counter = $state({ value: 0 })`, consumers do
  `counter.value++`) or explicit getter/setter functions, rather than a
  bare reassignable primitive binding -- this matches how the underlying
  reactive proxy actually needs to be interacted with from outside its
  defining module.
- Finish the migration consistently within a file: convert all props via
  `$props()`, remove leftover `export let`, and drop `$`-store syntax on
  any variable that is now a rune rather than a store.
- Add `$bindable()` to any prop a parent binds to with `bind:`.

## Pitfalls
- Wrapping every converted variable in `$derived.by(() => {...})` even
  when a simple expression would do adds unnecessary indirection and
  makes the component harder to read -- reserve `.by` for computations
  that need more than a single expression.
- Converting a shared store to `$state` inside a `.svelte.js` file but
  keeping some far-away consumer still importing it expecting a
  Svelte-store-shaped API (`.subscribe()`) breaks that consumer outright --
  audit all importers of a migrated module, not just the module itself,
  before considering the migration done.

## Verify
For each converted reactive statement, change the underlying dependency
at runtime (via the UI or a script) and confirm the derived value updates
without a page reload; for shared cross-module state, mutate it from one
consumer and confirm a different importing module observes the updated
value on its next render.
