---
name: send-on-closed-channel-panic
description: Fix a runtime panic from sending on or closing an already-closed channel, distinct from the separate class of goroutine-leak and deadlock channel bugs.
triggers: ["panic send on closed channel", "close of closed channel panic", "close of nil channel", "who is responsible for closing this channel", "double close channel panic"]
permissions: ["READ"]
---

## Symptom
The program panics at runtime with one of: `panic: send on closed channel`,
`panic: close of closed channel`, or `panic: close of nil channel`. This is
distinct from a deadlock or goroutine leak (the program doesn't hang, it
crashes immediately and loudly the moment the bad send/close executes), and
it's often intermittent in practice because it depends on the runtime
ordering between whichever goroutine closes the channel and whichever
goroutine(s) still try to send on it.

## Likely causes
1. **More than one goroutine can reach the code that closes a given
   channel**, and under some interleavings two different goroutines (or the
   same cleanup path triggered twice) both call `close(ch)` -- the second
   call always panics, regardless of timing, because closing an
   already-closed channel is unconditionally invalid.
2. **A producer goroutine keeps sending after a separate goroutine has
   already closed the channel** -- ownership of "who is allowed to close
   this channel" was never clearly established, so a consumer-side or
   timeout-triggered close races against a producer that doesn't know the
   channel is gone yet.
3. **A "close to signal cancellation" pattern is reused as a data channel**
   -- a channel is closed to broadcast a cancellation signal (a legitimate,
   idiomatic use of close), but the same channel is also used to send actual
   data values, so once it's closed for the cancellation signal, any
   in-flight data send on it panics.
4. **A zero-value (nil) channel field is closed before being initialized**,
   commonly in a struct whose channel field is only assigned inside a `Start`
   or `Init` method -- calling `Close()` on an instance that was never
   started calls `close()` on a nil channel, which panics immediately
   (distinct from *sending* on a nil channel, which blocks forever instead of
   panicking).

## Diagnose
- Read the exact panic message -- `send on closed channel` and `close of
  closed channel` point to different bugs (extra send vs. extra close) even
  though both stem from unclear channel ownership; `close of nil channel`
  points specifically to an uninitialized channel field, a different root
  cause entirely.
- Grep the codebase for every `close(ch)` call site for the specific channel
  variable in question -- if there is more than one call site (including
  ones reached via different code paths like a normal completion path and a
  separate error/timeout path), that's the direct candidate for a double
  close.
- Grep for every `ch <- value` send site for the same channel and check
  whether any of them can execute concurrently with, or after, a goroutine
  that closes it -- specifically look for a select statement with a
  `<-ctx.Done()` case that closes the channel racing against another
  goroutine's unconditional send.
- Run the reproduction under `go run -race` -- while this specific panic
  isn't itself a data race (it's deterministic given the actual order of
  operations), a concurrent-close-and-send bug is very often accompanied by
  an actual data race on other shared state nearby, so `-race` frequently
  surfaces the broader synchronization problem even when it doesn't flag the
  channel operation itself.

## Fix
Establish a single, clear owner for closing any given channel -- as a rule,
only the sender(s) should close a channel, never a receiver, and only one
goroutine should be responsible for calling close at all:
```go
func produce(out chan<- int, done <-chan struct{}) {
    defer close(out) // the single producer owns closing `out`
    for i := 0; ; i++ {
        select {
        case out <- i:
        case <-done:
            return // return (and defer fires) instead of any other goroutine closing `out`
        }
    }
}
```
When multiple producers must all finish before a channel is safely closed,
use a `sync.WaitGroup` and have a single dedicated goroutine close the
channel only after `Wait()` returns, rather than letting any individual
producer close it:
```go
var wg sync.WaitGroup
out := make(chan int)
for _, p := range producers {
    wg.Add(1)
    go func(p Producer) { defer wg.Done(); p.Send(out) }(p)
}
go func() { wg.Wait(); close(out) }() // exactly one closer, after all producers finish
```
For cancellation signaling specifically, use a dedicated `done chan
struct{}` closed exactly once (guarded by `sync.Once` if multiple call sites
might request cancellation) rather than closing the same channel used to
carry data values.

## Pitfalls
- Wrapping every `close(ch)` in a `recover()` to suppress the panic "fixes"
  the crash but hides a real ownership bug -- the program keeps running with
  channel semantics that are now unpredictable (was it actually closed? did
  the send before it succeed?) instead of surfacing the design flaw.
- Using `sync.Once` around a close call solves the double-close case but
  does nothing for the send-after-close case if a producer isn't also
  checking the same cancellation signal before sending -- the two failure
  modes need the same underlying fix (clear ownership + a shared done
  signal), not two independent patches.
- Checking channel state before sending with something like a non-blocking
  `select` with a `default` case to "detect" if it's closed is not reliable --
  there's no way to check "is this channel closed" without consuming a value
  or racing against a concurrent close between the check and the send; the
  fix is ownership discipline, not a runtime check.

## Verify
Write a test that starts the actual producer/consumer goroutine
configuration used in production (not a simplified single-goroutine stand-in)
and runs it repeatedly (`go test -run TestChannelLifecycle -count=200
-race`) under a scenario that exercises the cancellation/completion path
that used to race -- confirm zero panics and no `-race` reports across all
runs, since a single clean run does not rule out a timing-dependent
double-close or send-after-close.
