---
name: grpc-bidi-streaming-hang-unclosed-send
description: A bidirectional streaming gRPC call never completes because one side keeps its send direction open after it has nothing left to send.
triggers: ["bidirectional stream hangs", "grpc stream never completes", "client never gets final response streaming", "half close not called grpc", "stream stuck open forever"]
permissions: ["READ"]
---

## Symptom
A bidirectional streaming RPC (both client and server sending messages
independently over the same call) never reaches completion. The client
appears to hang waiting for a final status/trailer that never arrives, or
the server's handler loop blocks forever on `Recv()`/reading the next
message, even though both sides believe they've sent everything they
meant to send. Connection/goroutine/thread counts creep up over time as
stuck calls accumulate instead of completing and releasing resources.

## Likely causes
1. **The client (or server) never half-closes its send stream** after its
   last message -- gRPC's bidi model requires an explicit signal
   (`CloseSend()` in Go, completing the request observable/iterator in
   other languages) that "I am done sending," distinct from having sent
   the last message; without it, the other side's read loop has no way to
   know more messages *won't* arrive and keeps blocking on `Recv()`.
2. **The server's handler never returns** because it's stuck in a
   `for { msg, err := stream.Recv(); ... }` loop that only exits on an
   `io.EOF`-equivalent (which only comes from the client's half-close) or
   an error -- if the client never half-closes and never errors, the loop
   blocks indefinitely and the RPC (and its goroutine) never finishes.
3. **One side's send and receive loops run sequentially instead of
   concurrently** -- e.g. code that tries to fully drain incoming messages
   before starting to send, when the protocol actually requires
   interleaved send/receive (common when a request messages depends on a
   prior response) -- this deadlocks because each side is waiting for the
   other to send first.
4. **An error on one direction isn't propagated to unblock the other** --
   e.g. the send loop hits an error and exits, but nothing tells the
   receive loop (running as a separate goroutine/task) to stop waiting,
   so the call hangs even though it's effectively dead.

## Diagnose
- Identify which side of the specific hung call is blocked and where:
  server-side stack/goroutine dump showing a handler parked in
  `stream.Recv()`, or client-side showing it parked waiting on the
  response stream -- this tells you which half-close is missing.
- Check the client code path for every call site that can finish sending
  legitimately (success path, error path, cancellation path) and confirm
  each one calls the half-close/complete method before returning -- a
  common bug is calling it only on the success path and leaving it out of
  early-return/error branches.
- Check the server handler's read loop exit conditions -- confirm it
  actually distinguishes "client closed send, no more messages" (a clean
  end-of-stream signal) from "an error occurred" from "still waiting,"
  and that all three are reachable in code, not just the happy path.
- For suspected interleaving deadlocks, log a sequence number/timestamp
  on every send and receive on both sides and check whether the observed
  ordering shows both sides simultaneously waiting to receive with
  nothing in flight.

## Fix
- Always pair every "no more messages to send" state with an explicit
  half-close call, on every exit path (success, business error, and
  exception/panic-recovery paths alike) -- treat forgetting it as
  equivalent to forgetting to close a file handle.
- Run the send loop and receive loop concurrently (separate
  goroutines/tasks/threads, or an event-driven reactor) rather than
  sequentially, unless the protocol is strictly request-then-response per
  message -- and if it *is* strictly alternating, make that an explicit,
  documented state machine rather than an implicit assumption, since bidi
  streams don't enforce ordering between the two directions for you.
- When either direction errors, actively cancel the call (cancel the
  shared context) so the other direction's blocked read/write unblocks
  with an error immediately, instead of waiting for a timeout or hanging
  forever.
- Give every streaming call a maximum lifetime deadline as a backstop
  (even if individual messages have no natural timeout) so a
  protocol-level bug degrades to a bounded failure instead of an
  unbounded resource leak.

## Pitfalls
- Adding a client-side timeout that cancels the *call* but not fixing the
  underlying missing half-close -- this masks the symptom (the call now
  eventually errors out) without fixing the root cause, so server-side
  goroutines still pile up until the timeout fires, and any legitimate
  slow-but-valid stream now gets killed too.
- Calling half-close but continuing to call `Send()` afterward -- most
  gRPC implementations treat this as a programming error (panic or
  ignored send), so half-close must genuinely be the last send-side
  operation.
- Assuming `Recv()` returning an end-of-stream signal on one call implies
  the whole RPC is done -- in bidi streaming the two directions are
  independent; the server may still have messages left to send after the
  client half-closes, and must keep sending before it returns.

## Verify
Run the streaming call under a test that deliberately exercises every
send-loop exit path (success, mid-stream business error, immediate
cancellation) and confirm the call transitions to a final status (not a
hang) within a bounded time in each case, and that server-side
goroutine/thread/connection counts return to baseline after the calls
complete rather than trending upward.
