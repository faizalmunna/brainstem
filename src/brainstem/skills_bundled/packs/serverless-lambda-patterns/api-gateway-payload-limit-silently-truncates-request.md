---
name: api-gateway-payload-limit-silently-truncates-request
description: A request or response body silently fails or gets rejected because it exceeds the API gateway or function platform's hard payload size limit.
triggers: ["413 payload too large serverless", "lambda response too large error", "api gateway request body limit", "function output truncated unexpectedly"]
permissions: ["READ"]
---

## Symptom
A specific request that includes a larger-than-usual body (a file upload,
a bulk batch of records, a verbose JSON payload) fails with a 413, an
opaque platform error, or -- worse -- appears to "succeed" from the
client's perspective but the function never actually received the full
payload or the client only received a truncated response. Smaller
requests of the same type work perfectly, so the bug reads as
intermittent or data-dependent rather than a fixed, documented limit.

## Likely causes
1. **The API gateway/HTTP frontend in front of the function enforces its
   own payload size limit independent of the function platform's limit**
   (e.g., API Gateway's payload limit versus Lambda's own invocation
   payload limit), so a request can be rejected at the gateway layer
   before the function ever runs, and the function's own logs show
   nothing because it was never invoked.
2. **The function platform itself has a separate, often smaller, limit for
   synchronous versus asynchronous invocation payloads** (Lambda: 6 MB
   synchronous request/response, 256 KB for asynchronous event payloads),
   so the same logical function can behave correctly when called
   synchronously but silently fail or get throttled differently when
   invoked asynchronously with a larger event.
3. **The response payload, not the request, is what exceeds the limit** --
   a function that queries a data source and returns results directly
   without pagination can produce a response body that grows with data
   volume over time until it silently crosses the response size limit,
   which is a different failure mode than a request-side limit and is
   easy to overlook when only request size was considered.
4. **A base64-encoding step (common for binary payloads through API
   Gateway) inflates the effective payload size by roughly a third**, so a
   binary file that appears to be under the limit in its raw form actually
   exceeds it once encoded for transport, and size calculations done
   against the raw file size underestimate the real transmitted size.
5. **Client-side or intermediate proxy/CDN layers have their own,
   different size limits** that get hit before the request even reaches
   the API gateway, so the actual rejection point isn't where the team
   assumes it is, and troubleshooting the function/gateway configuration
   alone won't find it.

## Diagnose
- Reproduce the failure with a payload of precisely known size, and
  binary-search the size at which it starts failing, to determine the
  actual effective limit being hit rather than assuming which documented
  limit applies.
- Check the response status code and headers/logs at each layer
  separately -- the API gateway's own access logs, the CDN/proxy's logs if
  present, and the function's own invocation logs -- to identify exactly
  which layer rejected the request; a request that never appears in the
  function's own logs at all confirms rejection happened upstream of the
  function.
- If the payload involves binary data transported through a JSON-based
  gateway, recompute the actual transmitted size after base64 encoding
  (roughly raw size times 4/3) before comparing it against the documented
  limit, rather than comparing the raw file size.
- For response-side failures, check whether the failing case correlates
  with result set size (more rows, more matched records) rather than
  request size, and test with a deliberately large result set to confirm
  the limit is on the way out, not the way in.
- Check whether the specific request uses synchronous invocation
  (a direct HTTP-style call) versus asynchronous invocation (an event
  source) for the same function, since the size limits and failure
  behavior can differ meaningfully between the two paths even for the
  same underlying function code.

## Fix
For requests/responses that can legitimately exceed the platform's hard
limits, don't try to raise the limit (many of these are fixed platform
maximums, not configurable quotas) -- redesign the transfer to avoid
sending the large payload through the function invocation path at all:
use a pre-signed upload URL so large file uploads go directly to object
storage and the function receives only a reference, and paginate or
stream large result sets instead of returning everything in one response
body. Where base64 encoding of binary payloads is unavoidable through a
given transport, budget for its size inflation explicitly when checking
against limits, or use a binary-media-type passthrough configuration on
the gateway where supported to avoid the encoding overhead entirely.
Make size-limit failures visible and specific to the client (a clear 413
with a message stating the actual limit) rather than letting them surface
as a generic timeout or connection error, so callers can distinguish "you
sent too much data" from an actual server-side bug.

## Pitfalls
Assuming the limit encountered is the same one documented for the
"typical" invocation path (e.g., only checking the synchronous request
limit) when the actual failing call goes through a different path
(asynchronous, or through a different gateway type) with its own separate
and sometimes much smaller limit -- always confirm which specific limit
applies to the exact invocation path in question rather than pattern-
matching to the most commonly cited number. Also, working around a
response-size limit by compressing the response body can mask the
underlying design problem (returning too much data in one call) and will
eventually hit the limit again once the uncompressed data grows enough,
merely buying time rather than fixing the pattern.

## Verify
Send a request with a payload sized just above the previously failing
threshold through the redesigned path (pre-signed upload, or paginated
response) and confirm it completes successfully with the function
receiving/returning only a reference or a page of data, not the full
oversized payload directly; also send a request with a payload sized to
intentionally exceed the true limit and confirm the caller receives a
clear, specific error rather than a generic timeout or silent failure.
