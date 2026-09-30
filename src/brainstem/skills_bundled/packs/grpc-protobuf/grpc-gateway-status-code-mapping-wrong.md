---
name: grpc-gateway-status-code-mapping-wrong
description: A REST client behind a gRPC-gateway or transcoding proxy receives the wrong HTTP status code for a gRPC error, such as a client bug returning 500.
triggers: ["grpc gateway wrong http status", "grpc status maps to 500 incorrectly", "not found returns 500 through gateway", "grpc-gateway error code mismatch", "google.rpc.Status http mapping wrong"]
permissions: ["READ"]
---

## Symptom
A gRPC service returns a specific, correct gRPC status code (e.g.
`NOT_FOUND`, `INVALID_ARGUMENT`, `ALREADY_EXISTS`) for a well-understood
client error, but callers hitting the same logic through a gRPC-gateway
or HTTP/JSON transcoding layer see it surface as an unhelpful `500
Internal Server Error` (or some other mismatched code) instead of the
expected `404`, `400`, or `409` -- breaking REST clients' ability to
branch on status code, and polluting error-rate alerting meant to
separate client mistakes from real server failures.

## Likely causes
1. **A custom error being returned isn't a proper gRPC status at all** --
   the handler returns a plain Go `error`, a raised exception, or a panic
   recovery that the framework can't map to anything more specific than
   `Unknown`/`Internal`, because it was never constructed with
   `status.New(codes.NotFound, ...)` (or the equivalent in the server's
   language) in the first place.
2. **The gateway's default code-to-HTTP mapping table is being relied on
   for a code it doesn't map the way the API expects** -- the standard
   gRPC-to-HTTP mapping (per Google's API design guide) maps most codes
   sensibly, but a service using a less common code (e.g. `FAILED_PRECONDITION`,
   `ABORTED`, `OUT_OF_RANGE`) may find the default mapping doesn't match
   the semantics the REST consumers actually expect for that situation.
3. **An interceptor/middleware layer between the handler and the gateway
   wraps or replaces the original status** -- e.g. a panic-recovery
   interceptor that converts *any* recovered panic to `codes.Internal`
   regardless of what status the handler was in the middle of returning,
   or a logging interceptor that accidentally re-wraps the error and
   loses the original code.
4. **Error details (`google.rpc.Status` with attached `details`, such as
   `BadRequest` field violations) are set but the gateway/client isn't
   configured to surface them**, so the HTTP response has a technically
   correct top-level code but loses the structured detail that would let
   the REST client show a specific message instead of a generic one.

## Diagnose
- Call the RPC directly with a gRPC client (bypassing the gateway,
  e.g. `grpcurl`) for the failing case and confirm what status code the
  service actually returns at the gRPC layer -- this isolates whether the
  bug is in the handler's error construction or in the gateway's
  translation.
- If the gRPC-level code is already correct, check the specific
  gRPC-code-to-HTTP-status table the gateway implementation uses (e.g.
  grpc-gateway's `runtime.HTTPStatusFromCode`) against the code being
  returned, and confirm it matches expectations for that code -- don't
  assume without checking, since some codes (`ABORTED`, `OUT_OF_RANGE`)
  have mappings that surprise people.
- If the gRPC-level code is already wrong (e.g. `Unknown` or `Internal`
  when it should be `NotFound`), trace backward through any interceptors
  registered on the server to find where the original status gets lost --
  add a log statement immediately before the handler returns its error
  and compare it to what the outermost interceptor ultimately sends.
- Check whether the error was raised as a raw exception/panic anywhere in
  the call path rather than an explicit status construction -- language
  runtimes typically default uncaught exceptions to `Internal`/`Unknown`.

## Fix
- Construct every client-facing error as an explicit gRPC status with the
  correct code at the point the error condition is detected (not
  generic exceptions later caught and converted), using the language's
  status-with-details API (`status.Errorf(codes.NotFound, ...)` in Go,
  `grpc.StatusException` in Java, etc.) so the code survives
  serialization intact.
- Attach structured error details (`google.rpc.ErrorInfo`,
  `BadRequest`, `PreconditionFailure`) via `status.WithDetails(...)`
  rather than only a human-readable message string, and confirm the
  gateway is configured to forward these into the JSON error body (most
  transcoding layers support an error handler hook for this).
- Where the default code-to-HTTP mapping doesn't match the API's actual
  semantics, override it explicitly with a custom error handler
  registered on the gateway (grpc-gateway's `WithErrorHandler`, Envoy's
  gRPC-JSON transcoder filter config) rather than working around it
  ad hoc per endpoint.
- Make any panic-recovery or generic error-wrapping interceptor
  status-aware: if the recovered error is already a valid gRPC status,
  preserve it; only fall back to `Internal` for genuinely unexpected
  panics/exceptions that never had a status.

## Pitfalls
- Recovery middleware that unconditionally converts *all* caught
  errors/panics to `Internal` "to be safe" -- this is convenient for
  catching truly unexpected failures but destroys legitimate client-error
  signals (`NotFound`, `InvalidArgument`) that occurred deeper in the call
  and were already correctly classified before the panic handler saw them.
- Returning `codes.Internal` for validation failures because it's the
  path of least resistance -- this misclassifies client errors as server
  errors in monitoring/alerting, inflating server error-rate dashboards
  with problems that are actually bad client input.
- Assuming the gateway's default mapping table needs no verification --
  teams frequently discover only in production that a code like
  `FAILED_PRECONDITION` maps to `400` by default when their API contract
  documented it as `409`.

## Verify
Issue an HTTP request through the gateway that deliberately triggers each
distinct error path the service defines (not found, invalid argument,
already exists, permission denied, internal), and confirm both the HTTP
status code and the JSON error body's code/message/details match what the
API's documented contract promises for each one -- not just that an error
occurred.
