---
name: protobuf-oneof-silent-field-clearing
description: Setting one field inside a protobuf oneof unexpectedly clears a different field that was previously set on the same message.
triggers: ["oneof field cleared unexpectedly", "protobuf oneof overwrites other field", "setting field clears sibling oneof field", "oneof case switched unexpectedly", "lost data setting oneof"]
permissions: ["READ"]
---

## Symptom
Code sets one field that's part of a protobuf `oneof` group, and a
*different* field -- one the code never touched in that statement --
comes back empty/unset afterward, even though nothing appears to
explicitly clear it. This is often discovered as "data went missing"
during message construction or mutation, particularly when building a
message incrementally across several function calls or merging two
messages together.

## Likely causes
1. **This is `oneof`'s actual designed behavior being unfamiliar to the
   developer**, not a bug: setting any field in a `oneof` group
   automatically clears whichever other field in that same group was
   previously set, because a `oneof` guarantees at most one of its member
   fields is set at a time -- code written as if the fields were
   independent (setting `payment.card_details` earlier, then later
   setting `payment.bank_details` "in addition") loses the first field
   because both belong to the same `oneof`.
2. **A message is built incrementally across multiple layers/functions**
   that each assume they're the only one setting fields in that oneof,
   without any of them checking which case is currently active -- a
   later layer sets its own oneof member without realizing an earlier
   layer already populated a different one, silently discarding the
   earlier layer's work.
3. **Merging two messages (`proto.Merge` or equivalent) behaves
   differently for `oneof` fields than plain fields** -- merge semantics
   for a `oneof` take the *source* message's set case as a whole
   (replacing the destination's case entirely) rather than field-by-field
   merging, which surprises code expecting the same shallow-merge
   behavior it gets for non-oneof fields.
4. **A field was moved into a `oneof` during a schema refactor** without
   updating call sites that previously set multiple of those fields
   independently (safe before the refactor, silently lossy after),
   because the refactor is wire-compatible-looking but changes runtime
   semantics for existing code that sets more than one of the now-grouped
   fields.

## Diagnose
- Confirm the fields involved are actually declared in the same `oneof`
  block in the `.proto` file -- read the schema directly rather than
  assuming from field names, since oneof membership isn't visible from
  the generated struct/class shape alone in every language binding.
- Add a log/breakpoint immediately after each field-setting call in the
  suspect code path, printing which oneof case is active
  (`message.WhichOneof("group_name")` in Python,
  `.GetPayloadCase()`/`.getPayloadCase()` in Java, the generated
  `xxx_case()` in C++) -- this pinpoints exactly which statement flips
  the active case away from the one the code expected to keep.
- If the issue appears during a merge operation, isolate it: merge two
  minimal test messages that each set a different member of the same
  oneof and inspect the result's active case against what was expected --
  confirm whether "whole oneof replaced" or "merged" behavior is what's
  actually occurring for the library/language in use.
- Check whether the affected fields were recently moved into a shared
  `oneof` in a schema change, by diffing the `.proto` file history for
  that message.

## Fix
- Treat `oneof` membership as an explicit design decision that fields are
  mutually exclusive, and audit every code path that sets more than one
  member of the same oneof on the same message instance -- if the
  intent really is "these can coexist," they don't belong in the same
  `oneof` and the schema should be changed to separate fields instead.
- When building a message incrementally across multiple functions/layers,
  have each layer check `WhichOneof()` before setting a member of a
  shared oneof, and make an explicit decision (skip, overwrite with a
  warning, or restructure so only one layer owns that oneof) rather than
  setting blindly.
- For merge operations, read the specific library's documented oneof
  merge semantics rather than assuming field-level merging, and if the
  desired behavior is different (e.g. "prefer whichever message has this
  case set, regardless of merge order"), implement that explicitly rather
  than relying on default merge behavior.
- When refactoring existing independent fields into a new `oneof`, grep
  for every call site that sets any of the affected fields and confirm
  none of them set more than one in the same code path before shipping
  the schema change.

## Pitfalls
- "Fixing" the symptom by pulling the fields back out of the `oneof`
  without considering why they were grouped in the first place (often a
  deliberate mutual-exclusivity constraint, e.g. exactly one payment
  method) -- removing the oneof removes the compiler/schema-level
  guarantee along with the bug, potentially reintroducing an invalid
  "both set" state the oneof existed to prevent.
- Checking a oneof member's value against its zero value to infer whether
  it was "the one that's set" -- a oneof member can legitimately be set
  to its own zero value and still be the active case; use the generated
  `WhichOneof`/case accessor, never a zero-value check, to determine
  which member is active.
- Assuming oneof merge behavior is consistent across all language
  bindings and versions without checking -- subtle differences in
  "replace whole case" vs. "merge nested message fields within the same
  case" have existed across implementations and are worth confirming for
  the specific library version in use.

## Verify
Construct a message, set one member of the oneof, then set a different
member of the same oneof, and confirm via the generated case-accessor
(not a raw field read) that exactly the second member is active and the
first is cleared -- this is correct, expected behavior. Separately,
confirm that any code path intending to preserve an earlier oneof
selection actually checks the active case first and does not
unconditionally overwrite it.
