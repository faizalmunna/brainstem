---
name: protobuf-field-renumbering-wire-break
description: A protobuf field was reassigned a different tag number and clients still running the old schema now silently read the wrong values or drop the field.
triggers: ["field renumbered protobuf", "wrong value after proto change", "old client reads garbage field", "protobuf field number changed", "wire format broken after proto edit"]
permissions: ["READ"]
---

## Symptom
After a proto message is edited and redeployed, clients still running an
older build of the same `.proto` start reading the wrong field entirely --
a string shows up where an int was expected, a boolean flips unexpectedly,
or a field that used to populate now comes back empty -- even though
nothing about the *semantic* meaning of the field looks like it should
have changed. Deserialization doesn't error; it just silently produces
wrong data, because protobuf's wire format only knows field numbers, not
field names.

## Likely causes
1. **A field's number was changed** (e.g. someone reordered fields
   alphabetically, or renumbered during a "cleanup" refactor) -- the wire
   format encodes only the tag number, so old binaries interpret bytes
   tagged `3` as whatever field `3` used to mean, and new binaries write
   field `3` as something else entirely.
2. **A deleted field's number was reused for a new field** of a different
   type -- any message serialized by an old client that still sets the
   old field will be misdecoded by the new server as the new field, and
   vice versa, sometimes without a decode error if the wire types happen
   to be compatible (e.g. both varint).
3. **Field numbers were never reserved after deletion**, so a later,
   unrelated change accidentally reuses a retired number without anyone
   noticing during review, because nothing in the `.proto` file itself
   flags that number as off-limits.
4. **Two branches independently added new fields to the same message**
   and both picked the same next-available number, then one branch merged
   without a renumbering conflict being caught (proto files merge
   textually without semantic checks).

## Diagnose
- Diff the `.proto` file's field numbers (not just names) between the
  currently-deployed version and the one being rolled out --
  `git diff -- '*.proto'` and check every line with a `= <number>` for
  a changed number attached to an existing field name, or a reused number
  attached to a new name.
- Reproduce by serializing a message with the old `.proto` definition and
  deserializing it with the new one (or vice versa) in a scratch script --
  compare field-by-field against what was intended.
- If a specific field is reported as wrong in production, capture the raw
  wire bytes (log them before deserialization, or use `protoc --decode_raw`
  which decodes by tag number only, ignoring the schema) and check whether
  the tag number in the bytes matches what the *current* schema expects
  for that field name.
- Check whether a linter that enforces protobuf backward compatibility
  (e.g. `buf breaking`) is wired into CI at all -- its absence is usually
  why this reached production undetected.

## Fix
Treat field numbers as a permanent, append-only allocation, never a
cosmetic detail to tidy up:
- Never change an existing field's number once any client (including
  internal ones, staging, or archived data at rest) may have serialized
  messages against it -- rename the *field name* freely if needed
  (renaming is wire-compatible), but leave the number untouched.
- When removing a field, mark its number (and name, for JSON
  compatibility) as `reserved` in the message so no future edit can
  reuse it by accident:
  `reserved 3, 7 to 9; reserved "old_field_name";`
- Adopt a single source of truth for "next available number" (a comment
  block at the top of the message, or a generated allocation registry for
  large shared proto repos) so parallel branches don't collide.
- Add a schema-compatibility check (`buf breaking --against
  '.git#branch=main'` or `protolock`) as a required CI step that fails the
  build on any renumbering, type change, or unreserved deletion -- this
  turns the mistake into a merge-time error instead of a production
  incident.

## Pitfalls
- Assuming a "cleanup" renumber is safe because "nobody uses that field
  anymore" -- old *data at rest* (event logs, message queues, database
  blobs storing serialized protos) was written with the old numbering and
  will be misread the next time it's deserialized, even if no live client
  exists.
- Reserving the field name but forgetting to reserve the number (or vice
  versa) -- both are needed, since JSON-based transports key on name while
  binary wire format keys on number.
- Relying on code review alone to catch renumbering -- reviewers reliably
  miss a changed number buried in a large diff; only an automated
  breaking-change check catches it consistently.

## Verify
Run `buf breaking` (or equivalent) comparing the new `.proto` against the
last deployed version and confirm it reports zero breaking changes; then
serialize a message with the old-schema-compiled code and deserialize it
with the new-schema-compiled code, and confirm every field matches its
intended value, not just that decoding didn't throw.
