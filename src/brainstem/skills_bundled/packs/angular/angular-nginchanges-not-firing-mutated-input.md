---
name: angular-nginchanges-not-firing-mutated-input
description: Diagnose ngOnChanges never firing for an Input object even though the parent visibly changed one of its properties.
triggers: ["ngOnChanges not firing angular", "input change not detected object", "ngOnChanges skipped for nested property", "child component not notified of input change"]
permissions: ["READ"]
---

## Symptom
A child component's `ngOnChanges` lifecycle hook never runs (or runs once
and never again) even though the parent has visibly changed a property on
the object passed to that child's `@Input` -- this happens with the
default change-detection strategy, not just under `OnPush`, which rules
out `OnPush` as the cause when this is reported.

## Likely causes
1. **The parent mutates a property on the same object instance passed
   down** (`this.config.title = 'new'`) instead of assigning a new object
   -- `ngOnChanges` is driven by Angular's `KeyValueDiffer`/reference
   comparison at the binding level, not a deep-equality check, so
   changing a property on the *same* reference produces no `SimpleChanges`
   entry for that `@Input` at all.
2. **The `@Input` object is shared by reference across multiple
   components**, and a sibling (not the direct parent-child binding path)
   mutates it -- since no binding expression re-evaluated to a new
   reference, no component watching that `@Input` gets notified, even the
   one whose template used the mutated data.
3. **The value actually is being replaced with a new object, but on a
   nested property several levels deep**, and code elsewhere reads
   `changes.config.currentValue.nested.deep.field` assuming the *nested*
   field is what triggers `SimpleChanges`, when actually only the
   top-level `config` reference change is what `ngOnChanges` reports.
4. **The binding itself was never wired as a property binding** -- a
   template attribute written as `config="someExpression"` instead of
   `[config]="someExpression"` binds a literal string, so the "changing"
   JS value was never actually flowing into the `@Input` at all.

## Diagnose
- Log inside `ngOnChanges(changes: SimpleChanges)` unconditionally (not
  gated on a specific key) and trigger the parent's update -- if the hook
  doesn't fire at all, the problem is upstream at the binding/reference
  level, not inside the hook's logic.
- In the parent, log `Object.is(oldConfigRef, this.config)` right after
  the update code runs -- `true` confirms the object was mutated in
  place rather than replaced.
- Check the template for the binding syntax on the `@Input` in question --
  confirm it uses square-bracket property binding, not a bare attribute.
- If `ngOnChanges` does fire, log `changes.config.previousValue` versus
  `changes.config.currentValue` to see whether they're the same reference
  (again pointing at mutation) despite the hook technically running once.

## Fix
- Have the parent construct a new object (spread the previous value and
  override the changed field: `this.config = { ...this.config, title:
  'new' }`) whenever it updates data destined for an `@Input`, so the
  reference itself changes and Angular's binding check -- which
  `ngOnChanges` relies on -- actually notices.
- If multiple components need to react to a mutation on a shared object
  that can't reasonably be made immutable everywhere, move that shared
  state into a service exposing an observable or signal, and have each
  interested component subscribe/read from that instead of relying on
  `@Input`-driven change detection to propagate a mutation.
- Fix any incorrect attribute-vs-property-binding syntax so the value
  actually flows through Angular's input mechanism instead of being
  serialized as a static string.

## Pitfalls
- Switching to immutable updates for the top-level object while a nested
  object inside it is still mutated in place reproduces the same bug one
  level down for any component whose `@Input` is that nested object
  specifically -- immutability needs to hold at whichever level is
  actually bound as an `@Input`.
- Reaching for `ngDoCheck` with a manual deep-equality check as a
  workaround instead of fixing the mutation runs a potentially expensive
  comparison on every single change-detection cycle for that component,
  which can itself become a performance problem on a hot path.

## Verify
Trigger the parent's update again after switching to an immutable update
pattern, and confirm `ngOnChanges` now fires with `changes.config`
present, `previousValue` and `currentValue` referencing genuinely
different objects, and the child's template reflecting the new value.
