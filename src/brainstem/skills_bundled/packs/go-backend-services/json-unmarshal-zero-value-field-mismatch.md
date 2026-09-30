---
name: json-unmarshal-zero-value-field-mismatch
description: Fix a struct field that silently stays at its zero value after json.Unmarshal because the JSON key doesn't match the field name or struct tag.
triggers: ["struct field stays empty after unmarshal", "json field not populating", "json.Unmarshal silently ignores field", "struct tag mismatch json", "field always zero value from api response"]
permissions: ["READ"]
---

## Symptom
After calling `json.Unmarshal` (or decoding an HTTP response body into a
struct), one or more fields remain at their zero value (`""`, `0`, `false`,
`nil`) even though the source JSON clearly contains a value for that
logical field -- and critically, `Unmarshal` returns no error at all, because
by default it silently ignores JSON keys it can't match to a struct field
and leaves unmatched struct fields at their zero value.

## Likely causes
1. **Case or naming mismatch between the JSON key and the Go field name with
   no explicit tag** -- `encoding/json`'s default matching is case-insensitive
   for exact matches but does not know about `snake_case` vs `camelCase`
   conventions; a JSON key `user_id` will not match a Go field `UserID`
   without an explicit `json:"user_id"` tag.
2. **A struct tag typo** -- `json:"emial"` instead of `json:"email"`, or a
   stray space/quote issue in the tag string -- silently creates a field that
   matches nothing, since Go doesn't validate tag content at compile time.
3. **The field is unexported (lowercase first letter)** -- `encoding/json`
   can only see and populate exported fields; a lowercase field is invisible
   to it entirely regardless of tags, and this produces no error either.
4. **Nested/embedded struct shape doesn't match the JSON's actual nesting**
   -- e.g. the JSON has `{"address": {"city": "..."}}` but the Go struct
   embeds `Address` without a matching field name or tag, or expects the
   fields flattened at the top level.
5. **The JSON value's type doesn't match the field's type closely enough** --
   e.g. a JSON number arriving as a string (`"42"` instead of `42`) into an
   `int` field, which *does* produce an `UnmarshalTypeError`, but if that
   error is being ignored/discarded by calling code, it looks identical to
   the silent zero-value cases above from the caller's perspective.

## Diagnose
- Compare the raw JSON payload byte-for-byte against the struct's tags --
  don't compare against the Go field names, since those are irrelevant to
  matching once a tag is present. Print the raw response body
  (`io.ReadAll` before decoding, or `httputil.DumpResponse`) if the payload
  isn't already logged somewhere.
- Check whether `Unmarshal`'s returned `error` is actually being checked and
  logged at the call site -- a swallowed type-mismatch error looks
  identical to a silent tag-mismatch zero value; ruling this out first
  narrows the investigation.
- Use `json.Decoder` with `DisallowUnknownFields()` temporarily in a test (not
  necessarily in production, since it's stricter than may be desired there)
  to surface JSON keys that don't match any struct field -- this flips the
  silent-ignore default into a loud error during debugging.
- Confirm the field is exported (capitalized) and check its tag string
  character by character against the actual JSON key, including underscores
  and casing.

## Fix
Make every field's expected JSON key explicit with a tag, rather than relying
on Go's default case-insensitive name matching -- this makes the mapping
readable at a glance and immune to naming-convention mismatches:
```go
type User struct {
    ID    string `json:"user_id"`
    Email string `json:"email"`
    Addr  struct {
        City string `json:"city"`
    } `json:"address"`
}
```
During development, temporarily decode with `DisallowUnknownFields` in a unit
test against a real captured sample payload -- this catches both a Go-side
typo and a JSON-side schema change (an upstream API renaming a field) before
it ships as a silent zero-value bug. Always check and log/return the error
from `Unmarshal`/`Decode` rather than discarding it, since some mismatches
(type mismatches) do surface as real errors and shouldn't be silently
swallowed alongside the genuinely-silent tag-mismatch cases.

## Pitfalls
- Leaving `DisallowUnknownFields` enabled in production decoding of a
  third-party API response makes the integration brittle against the
  provider adding new fields (a normal, non-breaking API evolution) -- use
  it as a development/test-time check, not necessarily a permanent
  production setting, unless strict schema enforcement is genuinely desired.
- Fixing the tag but not adding a test means the same mismatch can silently
  reappear on the next refactor -- pin the expected mapping down with a test
  against a realistic fixture payload, not just a manual check during this
  debugging session.
- Assuming a populated *sibling* field means the whole struct decoded
  correctly -- `Unmarshal` populates whatever partially matches and silently
  leaves the rest zero-valued, so one correct field doesn't rule out others
  being silently wrong.

## Verify
Add a unit test that decodes a realistic, ideally real-captured, JSON
fixture into the struct and asserts every field (not just the one that was
broken) equals its expected value -- specifically including the field that
was previously silently zero, to lock in the tag fix against regression.
