---
name: sensitive-data-in-logs
description: PII, credentials, or other sensitive data ends up in logs/traces at runtime, creating a compliance or security exposure even though the source code has no hardcoded secrets.
triggers: ["pii in logs", "sensitive data leaked in logs", "password in log output", "compliance audit found data in logs", "credit card in log line"]
permissions: ["READ"]
---

## Symptom

A compliance review, security audit, or log-access incident reveals that
production logs contain sensitive data -- full request/response bodies
with passwords or tokens, customer PII (names, emails, addresses, payment
details), or session tokens -- readable by anyone with log access, which
is typically a much larger set of people than those authorized to see
that raw data directly. This is a runtime data-handling issue, distinct
from `secrets-in-source-control` (which is about credentials committed to
code/config, not data flowing through logs at request time).

## Likely causes

- **Whole request/response objects are logged for debugging** ("log the
  full payload if something goes wrong") without field-level filtering,
  so any sensitive field present in the payload gets logged along with
  everything else.
- **A generic error handler logs the full exception context**, which in
  many frameworks includes the full request object (headers, body,
  cookies) by default -- convenient for debugging, but it logs
  `Authorization` headers and session cookies right alongside the useful
  stack trace.
- **Log statements interpolate user-supplied data directly into message
  strings** without knowing what that data might contain, so a field that
  happens to hold a password (a failed login attempt logging the
  submitted credentials for "debugging") gets logged without anyone
  explicitly deciding that was okay.
- **Third-party libraries log more than expected** -- an HTTP client
  library's debug/verbose mode logging full request/response including
  auth headers, left enabled from a debugging session.
- **No log redaction/scrubbing layer exists** -- there's no
  defense-in-depth catching sensitive-looking patterns (fields named
  `password`, `token`, `ssn`, or credit-card-shaped number patterns)
  before they're persisted, so every single call site has to individually
  get this right with no safety net.

## Diagnose

1. Search recent logs for known sensitive field names and shapes
   (`password`, `token`, `authorization`, `ssn`, credit-card-number-like
   patterns, email-address patterns) to establish the actual current
   exposure, not just a theoretical risk.
2. Audit generic exception/error-handling middleware specifically -- this
   is the highest-yield single place to check, since one such handler
   logging full request context can leak sensitive data from every
   endpoint at once.
3. Check whether any third-party client libraries are running in a debug/
   verbose logging mode in production configuration.
4. Determine who actually has access to the log storage/search tool in
   question -- the severity of this issue scales with how broad that
   access is, which matters for prioritizing the fix and for any
   disclosure/compliance obligation.

## Fix

Add an explicit redaction/scrubbing layer in the logging pipeline (most
structured logging libraries and log processors support a redaction
step by field name pattern and by value pattern) as defense-in-depth,
so a mistake at an individual call site doesn't automatically become a
leak. Fix the generic exception/error handler specifically to log a
curated, known-safe subset of request context (method, path, status
code, a redacted header list) instead of the raw request object.
Establish an explicit allow-list convention for what's safe to log from
user-supplied data (IDs are generally fine, free-text fields and known
sensitive field names are not) rather than an implicit "log whatever
seems useful" habit, and turn off third-party library verbose/debug
logging modes in production configuration explicitly.

## Pitfalls

Don't treat this as solved by redacting a handful of specific fields
you already know about while leaving the underlying pattern (logging
raw request/response objects) in place -- the next new sensitive field
added to a payload reproduces the same leak unless the redaction is
structural (a scrubbing layer, a safe-by-default request logger), not a
one-off patch. Also, once sensitive data has already been logged, the
fix must include a data-retention/purge conversation for what's already
stored, not just stopping future occurrences -- check log retention
policy and whether historical logs need scrubbing or deletion for
compliance.

## Verify

Deliberately submit a request containing known test sensitive-looking
data (a fake password field, a fake SSN-shaped value) through the fixed
path and confirm the resulting log entry has it redacted, not just
absent by luck. Re-run the same search-for-sensitive-patterns audit used
in diagnosis against fresh logs after the fix to confirm the exposure
rate actually dropped, not just that the one known call site was patched.
