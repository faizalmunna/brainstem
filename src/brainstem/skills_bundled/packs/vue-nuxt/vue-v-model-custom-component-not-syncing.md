---
name: vue-v-model-custom-component-not-syncing
description: Fix v-model on a custom component that fails to update the parent's bound variable when the inner input changes.
triggers: ["v-model not updating parent", "custom component v-model not working", "update:modelValue not firing", "named v-model not syncing", "v-model two way binding broken"]
permissions: ["READ"]
---

## Symptom
Typing into (or otherwise interacting with) a custom child component
wrapped with `v-model="someValue"` in the parent doesn't change
`someValue`, or it only changes after an unrelated re-render, even though
the child visually appears to accept the input.

## Likely causes
1. **Event name mismatch**: default `v-model` in Vue 3 expects the child
   to emit `update:modelValue`, but the child emits something else
   (`change`, `input`, a custom name) that Vue's compiled `v-model` isn't
   listening for.
2. **The child mutates the received prop directly** (`props.modelValue =
   newVal`) instead of emitting an update -- this either throws a dev-mode
   warning about mutating a prop, or appears to work locally in the
   child's own re-render while never actually reaching the parent's real
   source of truth.
3. **A named `v-model:title="x"` binding** is used, but the child still
   declares/emits the default `modelValue`/`update:modelValue` pair
   instead of the matching `title`/`update:title` pair the named binding
   requires.
4. **The child intentionally buffers/debounces the emit** (e.g. only
   emitting on blur, or after a debounce timer), which looks like broken
   syncing when it's actually working, just not on every keystroke.

## Diagnose
- Open the child component's `defineProps`/`defineEmits` (or `emits`
  option) and confirm the exact prop name and event name pairing against
  the `v-model` directive used in the parent -- a plain `v-model` needs
  `modelValue`/`update:modelValue`; `v-model:foo` needs `foo`/
  `update:foo`.
- Add a `console.log` immediately before the `emit(...)` call in the
  child to confirm it fires on every relevant interaction with the
  expected payload.
- Use Vue devtools' component inspector to compare the prop's current
  value against the emitted event log side by side.

## Fix
Match the prop and event names exactly to the `v-model` variant used.
Never mutate the prop directly inside the child; instead expose a
writable `computed` with a `get` that reads the prop and a `set` that
emits the update (`const model = computed({ get: () => props.modelValue,
set: v => emit('update:modelValue', v) })`), binding the input's own
`v-model` to that computed. This keeps the input feeling locally
responsive while every change still routes back through the emit to the
real source of truth in the parent.

## Pitfalls
"Fixing" the direct-prop-mutation warning by copying the prop into local
reactive state once (`const local = ref(props.modelValue)`) without ever
emitting changes back makes the input locally functional but permanently
disconnects it from the parent -- the parent's bound variable never
updates again, which is often worse than the original warning because it
fails silently.

## Verify
Type into (or interact with) the child input and confirm, via a `{{ }}`
interpolation of the parent's bound variable rendered somewhere else on
the page (or a `watch` logging it), that it updates on the same
interaction -- not just visually inside the child component.
