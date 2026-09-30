---
name: proto3-zero-value-ambiguity
description: Code cannot tell whether a proto3 scalar field was explicitly set to its zero value or simply never set by the client at all.
triggers: ["proto3 can't tell if field was set", "zero value looks like unset field", "false vs not set protobuf", "proto3 optional needed", "field defaults to zero silently"]
permissions: ["READ"]
---

## Symptom
A service receives a proto3 message where a scalar field (an `int32`,
`bool`, `string`, or `enum`) is `0`/`false`/`""`/the first enum value, and
business logic can't distinguish "the client explicitly wants this value"
from "the client didn't set this field at all, so it defaulted." This
typically surfaces as a bug where a legitimate update meant to clear a
field (e.g. set a discount to `0`) is silently ignored because the
update-merge logic treats `0` as "no value provided," or conversely where
"not provided" is misinterpreted as an intentional `0`/`false` and
overwrites a value the client never meant to touch.

## Likely causes
1. **Proto3's original design has no wire-level presence for scalar
   fields** -- unlike proto2, a proto3 scalar that equals its default
   (zero/empty/false) is simply not written to the wire at all (to save
   bytes), so on the receiving end there is no way to distinguish "sent
   as zero" from "never touched" just from looking at the decoded struct's
   field value.
2. **`FieldMask`/partial-update semantics were assumed rather than
   explicitly implemented** -- a PATCH-style API that's supposed to
   update only the fields the client included expects some signal of
   which fields were actually present in the request, but the handler
   just applies every field in the decoded message directly onto the
   stored object, so unset fields blow away existing values with zeros.
3. **`optional` wasn't used on a field where "unset" is a meaningful,
   distinct state** -- proto3 added the `optional` keyword (generating a
   presence-check `has_<field>()`/wrapper type) specifically to restore
   wire presence for scalars, but the message was written without it,
   defaulting to the presence-less behavior.
4. **A wrapper type (`google.protobuf.Int32Value`, `BoolValue`, etc.) or
   `FieldMask` was chosen inconsistently across the API** -- some fields
   use presence-aware wrapper types and others use plain scalars for
   fields that have the same "distinguish unset from zero" requirement,
   producing inconsistent behavior across otherwise similar endpoints.

## Diagnose
- Identify which fields in the message actually need this distinction --
  not every zero-valuable field does; a field is only at risk if "the
  user explicitly chose zero/false/empty" is a meaningful, different
  outcome from "the user didn't mention this field," which is common in
  partial-update (PATCH) and toggle/flag-style fields.
- Check the `.proto` definition for those fields: are they plain scalars,
  or do they use `optional`, a wrapper message type
  (`google.protobuf.BoolValue`), or a `FieldMask` parameter alongside
  them?
- Reproduce directly: construct two requests, one that omits the field
  entirely and one that explicitly sets it to the zero value, serialize
  both, and inspect the raw bytes (`protoc --decode_raw`) -- if the field
  is a plain scalar, the two serialized messages are byte-identical
  wherever that field is concerned, confirming presence information was
  lost at encode time, not just mishandled later.
- Check the update-handling code for whether it merges by iterating
  "fields present in the incoming message" (correct, if presence is
  available) versus "fields whose value differs from Go/Java's zero
  value for the type" (a common but incorrect proxy that reintroduces the
  same ambiguity in application code even after using `optional`).

## Fix
- For any scalar field where "explicitly set to zero" must be
  distinguishable from "not provided," declare it `optional` in proto3
  (`optional int32 discount = 4;`) -- generated code then exposes a
  presence check (`HasDiscount()` / `has_discount()`) backed by real wire
  presence, restoring the proto2 behavior for just that field.
- For partial-update (PATCH-style) endpoints, use `google.protobuf.FieldMask`
  explicitly as a request parameter naming which fields the client
  intends to update, and have the handler apply only those named fields
  from the message -- rather than inferring intent from the field values
  themselves.
- Where broad presence-awareness is needed across many fields in a
  message not otherwise using `optional`, consider the standard wrapper
  types (`google.protobuf.Int32Value`, `BoolValue`, `StringValue`) which
  make "unset" an explicit `null`/absent value in the generated language
  binding, at the cost of slightly more verbose access (`.getValue()`
  instead of direct field access).
- Document, in the `.proto` file itself as a comment on the field,
  whichever presence strategy was chosen and why, since mixing strategies
  across a large schema is itself a source of the next version of this
  bug.

## Pitfalls
- Adding `optional` to every field "just in case" -- it has a real cost
  (extra generated presence-tracking fields/bitsets, slightly larger
  messages in some implementations) and signals to API consumers that
  every field's presence is semantically meaningful, which is misleading
  noise for fields where zero-vs-unset genuinely never matters.
- Using a wrapper type for a field but then unwrapping it into a plain
  scalar early in the handler "for convenience" -- this throws away the
  presence information the wrapper existed to preserve, right before the
  code that needed it.
- Inferring "was this field set" from a `FieldMask` the client didn't
  actually send (assuming a default of "update everything") -- silently
  treating a missing mask as "all fields" reintroduces the exact
  overwrite-with-zero bug the mask was meant to prevent.

## Verify
Send two otherwise-identical requests against the endpoint -- one
omitting the field entirely, one explicitly setting it to its zero value
-- and confirm the server produces two different, correct outcomes (the
omitted case leaves the existing stored value untouched; the
explicit-zero case updates it to zero), not the same outcome in both
cases.
