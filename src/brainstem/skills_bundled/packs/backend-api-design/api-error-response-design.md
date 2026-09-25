---
name: api-error-response-design
description: Design consistent, actionable API error responses, and diagnose bugs caused by inconsistent error shapes or overloaded status codes across an API.
triggers: ["inconsistent api errors", "which status code to use", "api error format", "client cant parse error", "generic 500 error not helpful", "error response design"]
permissions: ["READ"]
---

## Symptom
API clients can't reliably distinguish error types (validation failure
vs. not-found vs. permission-denied vs. server bug) because different
endpoints return errors in different shapes, use the same status code for
different meanings, or return `200 OK` with an error embedded in the body
-- forcing clients to write brittle, endpoint-specific error handling.

## Likely causes
1. **No shared error response schema** -- different endpoints (or
   different developers) independently invented their own error body
   shape (`{error: "..."}` vs `{message: "..."}` vs `{errors: [...]}`),
   so a generic client-side error handler can't work across the API.
2. **Status codes used inconsistently or incorrectly**: validation
   failures returning `500` instead of `400`/`422`; not-found returning
   `200` with an empty/null body instead of `404`; authorization failures
   conflating "not authenticated" (`401`) with "authenticated but not
   permitted" (`403`).
3. **Returning `200 OK` with a success:false field in the body** for
   actual failures, breaking HTTP-level tooling (caching, retries,
   monitoring) that keys off status codes.
4. **Error messages that don't distinguish machine-readable identity from
   human-readable text**, so clients end up string-matching on the
   message to detect specific error types, which breaks the moment
   wording changes or is localized.

## Diagnose
- Sample error responses across several different endpoints in the API
  and compare their shape and status codes for equivalent situations
  (e.g. a validation error on two different endpoints) -- inconsistency
  here confirms the root cause directly.
- Check whether any endpoint returns `200` for a logical failure, which
  is usually visible by grepping for a `success`/`ok` boolean field in
  response bodies.
- Check whether clients have written string-matching logic on error
  messages (a strong signal that no stable machine-readable error code
  exists).

## Fix
- Define one shared error response shape used by every endpoint, with at
  minimum: a stable machine-readable error `code` (e.g.
  `"validation_error"`, `"not_found"`, `"insufficient_permissions"`), a
  human-readable `message` for logging/debugging (not for clients to
  branch on), and space for field-level detail on validation errors
  (which field, what rule failed).
- Standardize status code usage: `400`/`422` for client input validation,
  `401` for missing/invalid authentication, `403` for authenticated-but-
  not-permitted, `404` for not-found, `409` for conflict (e.g. duplicate
  resource), `429` for rate limiting, `5xx` reserved for actual server-
  side failures, never for expected client-caused conditions.
- Never return `200` for a logical failure -- use the status code as the
  primary signal, with the error body as supporting detail, so
  HTTP-level tooling (monitoring, retries, caching) behaves correctly
  without needing to parse the body.
- Give clients a stable `code` to branch logic on, keeping `message` free
  to change wording/localization without breaking client error handling.

## Pitfalls
- Retrofitting a shared error shape onto an existing API without
  versioning it (see `rest-api-versioning-strategy`) breaks any client
  already parsing the old shape -- roll it out as an additive/versioned
  change, not a silent replacement.
- Making error `code`s too granular (a unique code per possible message)
  defeats the purpose -- clients should be able to handle a manageable,
  documented set of codes generically, falling back to a generic "unknown
  error" path for anything else.
- Exposing internal details (stack traces, database error text, internal
  identifiers) in error messages returned to clients is both a security
  risk and unhelpful noise -- log full detail server-side, return a
  sanitized message and code to the client.

## Verify
Pick two different endpoints that can produce the same *class* of error
(e.g. both have a required field) and confirm they now return the same
status code and error shape, differing only in the field-specific detail
-- and confirm no endpoint returns `200` for a documented failure case.
