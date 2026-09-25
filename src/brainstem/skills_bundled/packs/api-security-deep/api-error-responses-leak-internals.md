---
name: api-error-responses-leak-internals
description: An API's error responses expose stack traces, raw database error messages, or internal file paths that hand an attacker reconnaissance data for free.
triggers: ["API returning stack trace to client", "database error message exposed in response", "500 error leaks internal details", "error response reveals server file path"]
permissions: ["READ"]
---

## Symptom
A malformed request, an edge-case input, or a genuine server error produces a response body containing a full stack trace, a raw SQL error ("duplicate key value violates unique constraint users_email_key"), an internal file path (`/app/src/services/payment_processor.py, line 142`), a library/framework version banner, or an internal hostname/IP -- visible to any external caller, not just in server-side logs.

## Likely causes
1. **Debug mode is enabled in a production or production-adjacent environment** (Flask/Django `DEBUG=True`, a framework's default detailed-error page, an unhandled-exception middleware that was never configured for production), so the framework's default verbose error page is served directly to API clients.
2. **Database or ORM exceptions propagate uncaught to the API response layer** instead of being caught and translated into a generic error, so whatever the database driver's exception message contains (schema names, constraint names, sometimes query fragments) ends up in the HTTP response.
3. **A generic exception handler exists but includes exception details "to help debugging"** -- e.g. a catch-all handler that returns `{"error": str(exception)}` for every unhandled exception type, which is convenient in development and silently ships to production because it technically "handles" every error without anyone auditing what it reveals.
4. **Third-party/upstream service errors are passed through verbatim** -- when a call to an internal microservice or a payment processor fails, the API proxies that service's raw error body back to the external client instead of catching it and returning a sanitized error.

## Diagnose
- Check environment configuration for debug/verbose-error flags across every deployed environment that's internet-reachable, not just "production" by name -- staging/UAT environments with production-like data are a common miss.
- Send deliberately malformed requests (invalid JSON, wrong types, SQL-meta-characters in string fields, missing required fields) to each endpoint in a test environment and inspect the full response body, not just the status code, for stack traces or driver-level error strings.
- Grep the codebase for global/catch-all exception handlers and check exactly what they include in the response body (`str(e)`, `e.message`, `traceback.format_exc()`) versus what they log server-side only.
- Check any endpoint that proxies or wraps calls to internal services/third-party APIs for whether failure responses from the upstream are passed through unmodified.

## Fix
Separate what gets logged from what gets returned to the client, and make that separation structural rather than per-handler discipline:
- Disable framework debug/verbose-error modes in every internet-reachable environment, confirmed via environment-specific configuration checks in CI, not just a one-time manual setting.
- Implement one centralized error-handling layer that catches all exceptions at the API boundary, logs full details (stack trace, exception type, request context) server-side with a correlation/request ID, and returns to the client only a generic message plus that correlation ID (e.g. `{"error": "internal_error", "request_id": "abc123"}`) so support/security can look up the real detail without exposing it externally.
- Wrap all database and upstream-service calls in explicit exception handling that translates known error types into safe, generic API error codes (e.g. a unique-constraint violation becomes a `409 Conflict` with a field-level message, not the raw driver exception).
- When proxying to internal/third-party services, always transform their error responses through your own error-translation layer before returning to the client -- never pass an upstream body straight through.

## Pitfalls
Don't fix this by just wrapping the stack trace in a 200-with-error-field response instead of a 500 -- the leak is the content of the message, not the HTTP status code, and changing status alone still hands the attacker the same internal details.

## Verify
Trigger each major error class (validation failure, auth failure, database constraint violation, and an actually unhandled exception via a fault-injection test) against a staging deployment configured identically to production, and confirm every response body contains only the generic sanitized error shape plus a correlation ID -- with the real detail present only in server-side logs keyed by that same ID.
