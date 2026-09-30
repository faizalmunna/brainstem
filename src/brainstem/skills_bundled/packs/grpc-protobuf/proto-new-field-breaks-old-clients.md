---
name: proto-new-field-breaks-old-clients
description: A newly added protobuf field is treated as effectively required by server validation, causing older clients that predate the field to start failing.
triggers: ["old client breaks after adding proto field", "new field required older clients fail", "backward compatibility broken adding field", "rolling deploy breaks old clients grpc", "new proto field rejected as missing"]
permissions: ["READ"]
---

## Symptom
A new field is added to an existing, already-deployed protobuf message,
and shortly after the server rolls out validation or business logic that
depends on it, requests from clients that were built before the field
existed start failing -- rejected with a validation error, defaulted into
an unintended state, or (in more severe cases) silently mishandled -- even
though adding a field is supposed to be a backward-compatible change at
the wire-format level. The break is in application-level *assumptions*
about the new field, not in the wire format itself, which is why it slips
past a pure schema-compatibility check.

## Likely causes
1. **Server-side validation logic treats the new field as required**
   (rejecting the request if it's missing/zero) without accounting for
   the fact that proto3 has no wire-level "required" concept and old
   clients literally cannot send a field their compiled schema doesn't
   know exists -- the validation was written assuming all clients are
   already updated, which is never simultaneously true during a rolling
   deploy or for any client with a slower release cadence.
2. **Business logic branches on the new field's presence/value as if
   its absence signals something meaningful and unexpected**, rather than
   treating "absent" as "this is an old client, apply the pre-existing
   default behavior" -- e.g. a new `preferred_region` field where its
   zero value is treated as "explicitly requested region zero" instead of
   "client doesn't know about regions yet, use legacy routing."
2. **A new field was added inside an existing `oneof`**, changing which
   branch old clients' unrelated-but-adjacent set fields fall into, or
   was added in a way that shifts previously-implicit defaults once new
   server logic starts checking it.
3. **The new field's addition coincided with removing the old
   code path that previously handled its absence** -- the server used to
   have a sensible default behavior for "this concept doesn't exist yet,"
   but that fallback was deleted as part of shipping the new field,
   assuming (incorrectly) that all clients would already be updated by
   the time the server change went live.
4. **No compatibility window/rollout plan was used** -- server-side
   dependence on the new field's presence was deployed in the same
   release as the field's introduction, without staging a period where
   the server tolerates its absence while client adoption catches up.

## Diagnose
- Confirm whether the failure is a genuine wire-compatibility break (a
  parse/decode error -- rare, since adding a field is wire-compatible by
  design) versus an application-level validation/logic rejection tied to
  the field's presence or value -- check the actual error returned, not
  just that requests from old clients are failing.
- Identify the population of clients actually affected -- check client
  version/user-agent metadata on failing requests (if available) to
  confirm they predate the field's introduction, and check the fraction
  of total traffic they represent, which affects how urgently a
  compatibility shim is needed.
- Read the exact validation or branching code that inspects the new
  field and determine what it does specifically when the field is at its
  zero/default value -- distinguish "treats it as invalid" from "treats
  it as a valid but different-meaning value" from "correctly treats it as
  legacy/unset."
- Check whether the field was declared `optional` (with generated
  presence checking) -- if it wasn't, confirm the validation code has any
  way at all to distinguish "old client, field absent" from "new client,
  field explicitly set to zero," since without `optional` it structurally
  cannot.

## Fix
- Never make server behavior depend on a new field being present unless
  every client that could possibly call the endpoint is guaranteed to
  send it -- for a rolling deploy or any external/third-party client
  population, that guarantee essentially never holds on day one.
- Declare the new field `optional` and check presence explicitly
  (`has_<field>()`) rather than checking against the zero value, then
  branch: if absent, run the same legacy behavior that existed before the
  field was introduced; if present, use the new behavior -- this keeps
  old clients working indefinitely without requiring them to upgrade.
- Stage the rollout: ship the field and let clients begin adopting it
  while the server still fully supports its absence; only introduce
  server logic that assumes universal adoption after telemetry confirms
  old-client traffic has dropped to an acceptable/zero level, and
  document that cutover as its own explicit, monitored step.
- If a field is genuinely meant to become mandatory over time, communicate
  and version that as an intentional breaking change (a new API version,
  a deprecation notice with a timeline) rather than an incidental
  side effect of adding a field and later depending on it.

## Pitfalls
- Calling a field `required` in comments/documentation/API contracts
  without any actual mechanism enforcing that old clients send it --
  proto3 has no wire-level required fields, so "required" here is purely
  a promise the server can choose to violate against clients it doesn't
  control the release cadence of.
- Assuming all clients auto-update quickly (mobile apps, embedded
  systems, or third-party integrators are frequently pinned to old
  versions for long periods) -- server-side changes that assume near-term
  universal client adoption routinely underestimate the long tail.
- Fixing the immediate validation rejection by defaulting the missing
  field to a "safe-looking" non-zero value in the handler, without
  checking whether that default actually reproduces the old behavior
  correctly for every code path that reads the field downstream.

## Verify
Send a request built against the *pre-field* compiled schema (or a
hand-crafted message that omits the new field's bytes entirely) to the
current server and confirm it's accepted and produces the same
legacy-correct behavior as before the field existed, alongside a second
request from the *new* schema that explicitly sets the field and confirm
it gets the new behavior -- both must pass, not just the new-client case.
