---
name: aspnet-model-binding-silent-null-name-mismatch
description: An ASP.NET Core action method receives a null or default value for a property because the request's form field, query parameter, or JSON key name doesn't match the model property name, and model binding fails silently instead of erroring.
triggers: ["model property is always null", "form value not binding", "aspnet model binding silent failure", "action parameter always default value"]
permissions: ["READ"]
---

## Symptom

An ASP.NET Core controller action receives a request that clearly
contains the expected data (visible in the raw request body/form in
browser devtools), but the bound model object has a property that's
always `null`, `0`, or its default value inside the action method, with
no exception or validation error raised.

## Likely causes

- **A case or naming mismatch between the client-sent field name and the
  C# property name** that falls outside what the default binder's
  case-insensitive matching covers -- e.g. a client sending `user_id`
  (snake_case) against a property named `UserId` with no explicit
  `[JsonPropertyName]`/`[FromForm(Name = ...)]` mapping.
- **The binding source attribute doesn't match how the data was actually
  sent** -- a property expected via `[FromBody]` when the client sent
  form-encoded data, or `[FromForm]` expected when the client sent JSON.
- **A nested/complex object's properties aren't prefixed correctly** for
  form-data binding, where ASP.NET Core's default model binding convention
  expects `Address.Street` rather than a bare `Street` field name for a
  nested `Address` object.
- **Model binding silently fails validation-free** because the property
  type doesn't have a required-ness constraint (`[Required]`) or the
  model state isn't checked (`ModelState.IsValid`) before use, so a
  failed bind just results in a default value being used without any
  visible error.
- **Content-Type header mismatch** -- the client didn't set
  `Content-Type: application/json` (or set it incorrectly), so ASP.NET
  Core's content negotiation chose a different formatter than the one
  that would have parsed the body correctly.

## Diagnose

1. Log or inspect the raw incoming request (headers, exact body/form
   content) at the point it reaches the server, and compare field names
   character-for-character against the model's property names/binding
   attributes.
2. Check `ModelState.IsValid` and `ModelState` errors inside the action --
   a binding mismatch often does register as a model state error even
   when the property itself just silently defaults, and this is the
   fastest way to see explicitly what didn't bind.
3. Confirm the actual `Content-Type` header sent by the client matches
   the binding source attribute expected on the action (`[FromBody]`
   needs a body formatter that matches the content type, typically JSON).
4. For nested objects specifically, check the exact prefixed naming
   convention required for the binding source in use (form-encoding vs.
   JSON have different nesting conventions).

## Fix

Add explicit binding attributes (`[FromForm(Name = "...")]`,
`[JsonPropertyName("...")]`) wherever the client's field naming
convention doesn't match the C# property naming convention by default,
rather than relying on implicit matching that's easy to break silently
during a refactor. Always check `ModelState.IsValid` at the start of an
action that depends on bound data and return a clear `400 Bad Request`
with the model state errors when it's invalid, instead of proceeding with
default values. Make required properties genuinely `[Required]` (or use
non-nullable value types without a default that could pass as valid) so
a missing/mismatched field surfaces as a validation error rather than a
silent default.

## Pitfalls

Don't respond to this by making every property nullable and defensively
null-checking everywhere in business logic -- that hides the actual bug
(the client and server disagreeing on a contract) behind runtime
null-guards instead of catching it at the API boundary where it belongs.
Also, when adding `[JsonPropertyName]`/`[FromForm(Name = ...)]` mappings,
keep them consistent with whatever's documented in the API contract/
OpenAPI spec -- a mapping that fixes binding but silently diverges from
published documentation just moves the mismatch to be between the docs
and the implementation instead.

## Verify

Send a request with the exact field names/content-type the fix now
expects and confirm the property binds correctly; then send a request
with a deliberately mismatched field name and confirm it now produces a
clear `400` validation error via `ModelState` instead of silently
defaulting. Check any existing client integrations (frontend forms, API
consumers) against the now-explicit binding names to confirm none of them
were relying on the old, accidentally-different mismatched behavior.
