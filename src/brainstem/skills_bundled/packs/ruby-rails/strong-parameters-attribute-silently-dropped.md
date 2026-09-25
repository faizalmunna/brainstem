---
name: strong-parameters-attribute-silently-dropped
description: Fix a form field or API payload attribute that saves as nil or unchanged because strong parameters silently filtered it out.
triggers: ["field not saving rails", "strong parameters dropping attribute", "form submits but attribute stays nil", "unpermitted parameter rails log", "nested attributes not saving rails"]
permissions: ["READ"]
---

## Symptom
A form submission or API request appears to succeed (no error, a 200/302
response, the record saves) but one specific attribute never actually
changes in the database -- it stays `nil` or keeps its previous value --
and the only clue is an easy-to-miss
`Unpermitted parameter: :the_attribute` line in the Rails log, which
doesn't raise by default.

## Likely causes
1. **The controller's `permit` list simply doesn't include the attribute**
   -- often because the attribute was added to the model/migration after
   the `permit` call was written, or because it was copy-pasted from a
   similar-but-different form that has a different set of fields.
2. **The attribute is nested inside a hash or array in the submitted
   params (a nested form, `accepts_nested_attributes_for`, or a JSON API
   payload with a nested object), but the `permit` call only lists it as
   a top-level scalar** -- nested attributes need their own nested
   `permit` structure (`permit(:name, address_attributes: [:street, :city])`),
   and a flat `permit(:name, :address)` silently drops the nested hash
   entirely.
3. **The form field's HTML `name` attribute doesn't match what the
   controller expects** (a typo, a stale `form_for`/`form_with` field
   name after a model attribute rename, or a dynamically-generated field
   name that doesn't match the nested attributes convention Rails
   expects, like a missing `[]` for an array of nested records) -- the
   parameter arrives under a different key than the one being permitted,
   so it's not that permit is wrong, it's that the key never matches.
4. **A `before_action` or serializer strips/renames the attribute before
   it reaches the `permit` call** -- e.g. a custom JSON parsing middleware,
   an API gateway, or a `to_param`-style transformation upstream that
   changes the payload shape between what the client sent and what
   `params` contains inside the controller.

## Diagnose
- Search the development log for the exact request and look for
  `Unpermitted parameter(s): ...` -- this line names the dropped attribute
  directly and is the fastest confirmation this is a strong-parameters
  issue rather than a validation or JS issue.
- In the controller action (temporarily, in a console/debugger, or via a
  log line), print `params.to_unsafe_h` (raw, before permit) versus the
  result of the actual `permit` call -- compare the two to see exactly
  what's being filtered out.
- Check the model for `accepts_nested_attributes_for` and confirm the
  controller's `permit` call includes the matching `_attributes` key with
  its own array of allowed nested keys, not just the association name.
- Inspect the actual HTML form's rendered field name (view source, or the
  request payload in browser devtools Network tab) and compare it
  character-for-character against what the controller's `permit` list and
  the model's attribute name expect.

## Fix
- Add the missing attribute (or nested `_attributes` structure) to the
  `permit` call, matching the exact shape of the incoming params --
  scalar attributes as bare symbols, nested/array attributes as a hash
  key mapping to an array of their own permitted keys.
- When the same set of permitted params is used in multiple actions
  (create/update), extract it into a private method
  (`def resource_params; params.require(:resource).permit(...); end`) so
  there's exactly one place to update when a new attribute is added,
  instead of several near-duplicate `permit` calls drifting out of sync.
- For dynamic/variable attribute sets (e.g. a configurable set of custom
  fields), avoid trying to enumerate every possible key in `permit` --
  instead validate and permit a known container key
  (`permit(custom_fields: {})` for an open hash, used deliberately and
  narrowly) and validate its contents in the model, rather than
  widening `permit` in ways that reintroduce mass-assignment risk.
- Add a request spec that submits the exact real-world form/payload shape
  (not a simplified hand-built params hash) so a future attribute added
  to the model without updating `permit` fails a test instead of shipping
  silently.

## Pitfalls
- Reaching for `params.permit!` (permitting everything) to make the
  immediate error go away reopens the exact mass-assignment
  vulnerability strong parameters exists to prevent -- never do this on a
  user-facing or externally-reachable endpoint.
- Fixing the `permit` list for `create` but forgetting `update` (or vice
  versa) when they're implemented as separate, not-quite-identical method
  calls -- consolidate into one shared params method wherever the
  permitted set is genuinely the same.
- Silencing the `Unpermitted parameter` log line (by changing
  `config.action_controller.action_on_unpermitted_parameters` to `:log`
  from `:raise`, or ignoring it) fixes the symptom's visibility, not the
  bug -- in development/test, prefer `:raise` so a missing attribute fails
  loudly during development instead of quietly logging in production.

## Verify
Submit the real form (or the real API payload shape, including nested
attributes if applicable) end-to-end and confirm, by re-fetching the
record afterward, that the specific attribute actually changed to the
submitted value. Add a request spec asserting the same, and confirm no
`Unpermitted parameter` line appears in the log for that request.
