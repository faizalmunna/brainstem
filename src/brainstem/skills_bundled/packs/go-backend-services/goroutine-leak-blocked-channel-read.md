---
name: goroutine-leak-blocked-channel-read
description: Diagnose a Go service whose goroutine count climbs monotonically because worker goroutines block forever reading from a channel that is never closed or written to again.
triggers: ["goroutine count keeps growing", "goroutine leak", "goroutines never exit", "memory grows slowly in production go service", "pprof shows thousands of goroutines"]
permissions: ["READ"]
---

## Symptom
A long-running Go service's goroutine count (visible in `/debug/pprof/goroutine`
or a metrics dashboard) climbs steadily over hours or days and never comes back
down, usually paired with slowly climbing memory (each blocked goroutine keeps
its stack and any captured closures alive). The process doesn't crash
immediately -- it just gets slower and eventually OOMs or is restarted.

## Likely causes
1. **A worker goroutine ranges over or reads from a channel that the producer
   side stops writing to without ever closing** -- `for v := range ch` or
   `v := <-ch` blocks forever once the last value is sent, because nothing
   signals "no more values are coming."
2. **A fan-out pattern spawns one goroutine per request/item to send on a
   shared result channel, but the receiver stops reading early** (e.g. it got
   the first result it needed and returned) -- every other sender goroutine is
   now permanently blocked on an unbuffered channel send with no reader.
3. **A context is created for cancellation but the goroutine's select never
   actually includes `<-ctx.Done()`** -- it only selects on the data channel,
   so cancelling the context does nothing to unblock it.
4. **An error path returns early without draining or closing a channel** that
   other goroutines are still writing to, so those writers block on send
   forever even though the consumer has moved on.

## Diagnose
- Hit `/debug/pprof/goroutine?debug=2` (requires `net/http/pprof` imported) on
  a suspect instance and read the stack traces -- look for many goroutines
  parked at the same line, in `chan receive` or `chan send` state, all
  originating from the same call site.
- Grep that call site for the channel's producer: confirm whether `close(ch)`
  is ever called on it, and on which code paths (success only? error paths
  too?).
- Check every `select` in the blocked goroutine for a `case <-ctx.Done():`
  branch -- if it's missing, cancellation cannot unblock it regardless of
  what the caller does.
- Reproduce locally with `GODEBUG=schedtrace=1000` or a simple counter of
  `runtime.NumGoroutine()` logged periodically while driving the code path
  that early-returns (e.g. cancel a request mid-flight, or hit an error
  branch) and confirm the count doesn't drop back down afterward.

## Fix
Treat "who closes the channel, and on every exit path" as a design question,
not an afterthought: the producer (the side with the send) should close the
channel exactly once, after it has stopped sending, including on error/early
return paths -- typically via `defer close(ch)` right after the channel is
created, so every return path (success, error, panic recovery) closes it. On
the consumer side, always select on `ctx.Done()` alongside the data channel:
```go
select {
case v, ok := <-ch:
    if !ok { return } // channel closed, producer is done
    handle(v)
case <-ctx.Done():
    return ctx.Err()
}
```
For fan-out/fan-in patterns where the receiver may stop early, make the send
side also select on `ctx.Done()` (or a dedicated `done` channel) so a sender
blocked on an unbuffered channel can abandon the send instead of blocking
forever:
```go
select {
case results <- res:
case <-ctx.Done():
    return
}
```

## Pitfalls
- Closing a channel from the *receiver* side, or from more than one goroutine,
  panics with "close of closed channel" or "send on closed channel" -- only
  the single sender/producer should ever close it, enforced by a comment or a
  wrapper type if multiple people touch this code.
- Adding a buffered channel to "fix" the leak just delays it -- if the
  consumer still never reads and the channel never closes, goroutines leak
  once the buffer fills instead of immediately; buffering isn't a substitute
  for a done/cancellation signal.
- Using `context.Background()` instead of propagating the caller's context
  into the worker goroutine defeats the `ctx.Done()` fix entirely, since that
  context can never be cancelled.

## Verify
Add a `runtime.NumGoroutine()` log line (or scrape it via pprof) before and
after driving the previously-leaking path N times (e.g. cancel 100 in-flight
requests, or trigger the early-return error branch 100 times), and confirm
the count returns to baseline within a few GC cycles rather than growing by
roughly N each time.
