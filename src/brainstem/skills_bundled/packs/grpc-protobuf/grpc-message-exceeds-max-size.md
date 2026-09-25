---
name: grpc-message-exceeds-max-size
description: A gRPC call fails with an unclear error or silently truncates data because the serialized message exceeds the configured maximum message size.
triggers: ["grpc resource exhausted message size", "grpc message too large", "received message larger than max", "grpc call fails large payload", "proto message size limit exceeded"]
permissions: ["READ"]
---

## Symptom
A gRPC call that worked fine with small payloads starts failing once a
request or response grows past a certain size -- either with an explicit
`RESOURCE_EXHAUSTED` error mentioning message size, or (worse) with a
generic transport-level failure, a connection reset, or in some
misconfigured setups, a response that appears to succeed but is silently
truncated. This typically appears only for specific inputs (a large list,
an embedded file, a big batch) rather than every call, making it look
intermittent.

## Likely causes
1. **The response (or request) genuinely exceeds gRPC's default max
   message size** (4 MiB in most official implementations) -- e.g. a
   list endpoint that returns "all rows" without pagination, or a field
   carrying an embedded blob/file, grows past the limit as the underlying
   dataset grows, so it worked in development/small-scale testing and
   fails only once real data volume is reached.
2. **Client and server have mismatched max-size settings** -- the server
   was configured with a larger `MaxRecvMsgSize`, but the client's
   `MaxRecvMsgSize` for the response (or `MaxSendMsgSize` on the sending
   side) was left at the library default, so the call fails on the
   client side even though the server would have accepted or sent it
   fine.
3. **An intermediate proxy or load balancer enforces its own, smaller
   message/body size limit** independent of the gRPC client/server
   configuration -- e.g. an API gateway, Envoy, or a cloud load balancer
   with a default max request/response size that's smaller than what
   the gRPC endpoints themselves were configured to allow, producing a
   failure that looks like a gRPC error but actually originates at the
   proxy.
4. **The design itself is unary-request/unary-response for inherently
   large or unbounded data** (bulk export, large file transfer) instead
   of using streaming, so *any* size limit set is eventually going to be
   exceeded as the use case grows -- raising the limit treats the symptom
   without addressing that unary RPCs aren't a good fit for unbounded
   payloads.

## Diagnose
- Read the exact error: `RESOURCE_EXHAUSTED` with a message like
  "received message larger than max" identifies this precisely and names
  which side (send vs. receive) and which size was measured versus the
  limit -- don't guess before reading it.
- Log the actual serialized size of the request/response in question
  (most language bindings expose this, or compute
  `proto.Marshal(msg)` length directly) and compare it against both the
  client's and server's configured `MaxSendMsgSize`/`MaxRecvMsgSize`.
- Check both ends' channel/server construction code for explicit
  message-size options -- if neither side sets them, both are on the
  library default (commonly 4 MiB), and the fix is different depending on
  whether one side already overrides it and the other doesn't.
- If failures happen intermittently or only in certain network paths,
  check for a proxy/load balancer/API gateway sitting between client and
  server and inspect its own body-size limit configuration independently
  of the gRPC application settings.

## Fix
- Set matching, explicit `MaxSendMsgSize` and `MaxRecvMsgSize` on both
  client and server for any endpoint expected to carry payloads near or
  above the default -- raising the limit on only one side doesn't help if
  the other side's default is what's rejecting the message.
- Also raise the limit on any intermediary in the path (reverse proxy,
  API gateway, service mesh sidecar) to be at least as large as the
  gRPC-level limit, since the smallest limit anywhere in the chain wins.
- For genuinely large or unbounded payloads (bulk data, file transfer),
  redesign the RPC as a server-streaming or client-streaming call that
  sends the data in bounded chunks, rather than continuing to raise a
  unary message size ceiling that will eventually be hit again as data
  grows.
- Where the payload is naturally paginated data (a list endpoint), add
  proper pagination (page tokens, page size limits) instead of raising
  message size limits to accommodate returning everything at once.

## Pitfalls
- Raising the max message size arbitrarily high (e.g. to hundreds of MB)
  as a blanket fix -- this doesn't just mask the underlying design issue,
  it also increases per-call memory pressure on the server (which must
  buffer the entire unary message) and creates a new availability risk
  under concurrent large requests.
- Fixing only the client-side or only the server-side limit and assuming
  the call will now succeed -- both sides enforce independently, and the
  smaller of the two (plus any proxy in between) is the effective limit
  for the whole call.
- Switching to streaming to work around the size limit but still
  buffering the entire dataset in memory before/after the stream (e.g.
  collecting all chunks into one big list on the receiving end) --
  this defeats the purpose of streaming, which is to bound memory usage,
  not just to satisfy a wire-level size check.

## Verify
Send a request (or trigger a response) sized deliberately just above and
just below the intended limit on both client and server, and confirm the
below-limit case succeeds end-to-end through every hop (including any
proxy) while the above-limit case fails with a clear, expected error
rather than a timeout, silent truncation, or connection reset.
