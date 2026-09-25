---
name: vue-reactivity-lost-on-destructure
description: Diagnose local variables that stop updating after destructuring properties off a reactive() object or props in Vue 3.
triggers: ["lost reactivity after destructuring", "reactive object stops updating", "destructured props not reactive", "toRefs not working", "vue variable not updating"]
permissions: ["READ"]
---

## Symptom
After writing `const { count } = state` (where `state` came from `reactive()`)
or `const { title } = props`, the local variable `count`/`title` holds the
value at the moment of destructuring and never changes again, even though
the template or a watcher on `state.count` clearly shows the source
updating.

## Likely causes
1. **Destructuring a `reactive()` object directly** copies out the current
   primitive value into a plain variable -- the Proxy that makes `reactive`
   work is bypassed entirely, so there's no link left to track.
2. **Destructuring `props` in `setup()`** to pass individual fields into a
   composable, losing the reactive connection to the parent unless each
   field is wrapped in `toRef`/`toRefs` first.
3. **Passing a destructured plain value into a composable** that expects a
   `Ref` (e.g. `useFetch(url)` where `url` was destructured out of a
   reactive params object) -- the composable can only track a real `Ref`,
   not a value that already stopped being reactive by the time it arrived.
4. **Reassigning a destructured array element** from a `reactive()` array
   instead of mutating the array in place, which detaches that element
   from the original reactive source.

## Diagnose
- Log the destructured variable with `console.log(isRef(count), count)` --
  if it's not a `Ref` and not changing, the link is already gone at the
  point of destructuring, not later.
- Open Vue devtools' component inspector and watch the source `state`
  object's property update live; if the destructured local variable in
  your component's data panel doesn't move in lockstep, the disconnection
  happened at destructuring time.
- Grep the file for `const { ... } = reactive(...)`, `const { ... } =
  props`, or `const { ... } = someReactiveThing` to find the exact
  destructuring site causing the loss.

## Fix
Use `toRefs(state)` when destructuring a whole reactive object, or
`toRef(state, 'count')` for a single field -- both return real `Ref`
objects that stay linked to the original source's property via a getter/
setter pair, so `count.value` continues to reflect `state.count`. For
props specifically, always go through `toRefs(props)` or `toRef(props,
'field')` rather than plain destructuring before handing a value to a
composable. If you don't need to destructure at all, prefer keeping the
whole object and accessing `state.count` directly -- this is the simplest
fix when the object is only read a couple of times.

## Pitfalls
Calling `toRefs()` on a plain object that was never wrapped in
`reactive()` in the first place silently returns disconnected refs that
never update -- `toRefs` only preserves a link that already exists, it
doesn't create reactivity out of nothing. Also, calling `toRefs` on a
very large object to destructure just one or two fields creates a ref for
every property eagerly; prefer `toRef` for single fields.

## Verify
Mutate the source property from outside the component (e.g. via an
action, a devtools console call, or a sibling component) and confirm the
destructured `ref`'s `.value` updates and the template re-renders,
without needing to re-destructure or remount the component.
