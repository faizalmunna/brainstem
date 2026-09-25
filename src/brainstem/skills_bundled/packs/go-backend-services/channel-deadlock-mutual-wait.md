---
name: channel-deadlock-mutual-wait
description: Resolve a full process hang, often reported by the Go runtime as fatal error, all goroutines are asleep, caused by two goroutines each blocked waiting on a channel the other should write to.
triggers: ["all goroutines are asleep deadlock", "fatal error all goroutines asleep", "program hangs on unbuffered channel", "two goroutines waiting on each other", "deadlock on channel send"]
permissions: ["READ"]
---

## Symptom
The program hangs completely and either the Go runtime prints `fatal error:
all goroutines are asleep - deadlock!` and exits (when *every* goroutine is
blocked, detectable by the runtime), or -- more commonly in a real server with
other live goroutines (HTTP listener, GC, timers) -- it just hangs
indefinitely on one request or one code path with no crash and no log output,
because the runtime only detects deadlock when *all* goroutines are stuck, not
when just two of them are.

## Likely causes
1. **Two goroutines each send on an unbuffered channel the other is expected
   to receive from, but both try to send before either tries to receive** --
   classic mutual wait, since an unbuffered send blocks until a matching
   receive is ready.
2. **A goroutine sends on channel A and then tries to receive on channel B,
   while the other goroutine does the mirror image** (send on B, then receive
   on A) -- if both sends happen first, both are now permanently blocked
   waiting for a receive that will never come because the receiver is itself
   blocked on its own send.
3. **A single goroutine sends and receives on the same unbuffered channel
   without ever yielding to another goroutine that would receive/send** -- a
   simplified but common version: `ch <- v` immediately followed by `<-ch` in
   the same goroutine with nothing else scheduled to consume it, which
   deadlocks trivially.
4. **A `sync.Mutex` is locked, and the goroutine then blocks on a channel
   operation while holding it, while a second goroutine needs that same mutex
   to proceed to the point where it would perform the channel operation the
   first goroutine is waiting on** -- a lock-then-channel-wait cycle, not a
   pure channel deadlock, but presents identically as a hang.

## Diagnose
- If the process actually crashed, read the `fatal error: all goroutines are
  asleep - deadlock!` dump -- it prints every goroutine's stack, so identify
  the two (or more) goroutines blocked in `chan send` / `chan receive` and
  read off exactly which channel variable each is blocked on.
- If it's a partial hang (server otherwise alive), send `SIGQUIT` to the
  process (or hit `/debug/pprof/goroutine?debug=2` if pprof is wired up) to
  get a full goroutine dump without killing it, then look for the same
  pattern: two goroutines parked on channel ops that reference each other's
  expected counterpart.
- Draw the wait-for graph by hand from the two stack traces: goroutine A is
  blocked wanting an action from goroutine B, and goroutine B is blocked
  wanting an action from goroutine A -- if it's a cycle, it's a deadlock, not
  a slow path.
- Check whether the channels involved are unbuffered (`make(chan T)`) --
  unbuffered send/receive pairs are the most common source since they require
  a synchronization rendezvous, unlike buffered channels which can absorb a
  temporary ordering mismatch.

## Fix
Break the cycle by removing the mutual dependency, not by papering over it
with a larger buffer (which only raises the load threshold at which the same
deadlock reappears). Concretely:
- Reorder so at least one side never blocks waiting on the other before it has
  done its part -- e.g. have one goroutine's send happen in its own goroutine
  (`go func() { ch <- v }()`) so the calling goroutine can proceed to receive
  without both sides waiting on each other in lockstep.
- Use a `select` with a `default` or a timeout on at least one side to detect
  and recover from the cycle rather than block forever, when an occasional
  race between the two is expected and recoverable.
- Redesign around a single coordinator goroutine that owns the channel
  operations for both directions in a well-defined order, if the true
  requirement is "exchange values between exactly two goroutines" --  this
  removes the possibility of misordering entirely, since one place decides
  the order.
- If the cycle involves a mutex plus a channel wait, never hold a lock across
  a blocking channel operation -- release the mutex before waiting on a
  channel, and re-acquire it after, or restructure so the channel operation
  doesn't need the lock held.

## Pitfalls
- "Fixing" the deadlock by switching an unbuffered channel to a large buffered
  one hides the bug until load increases enough to fill the buffer -- treat
  it as a design smell, not a real fix, unless the buffer size is chosen for
  a specific, justified reason (e.g. known max batch size).
- Adding a `time.Sleep` before the send/receive to "give the other goroutine
  time" is not a fix -- it reduces the probability of hitting the deadlock
  under light load and reintroduces it flakily under heavier load or on a
  slower machine/CI runner.
- Using `select` with `default` to avoid blocking can silently drop the value
  instead of actually resolving the ordering problem -- only appropriate when
  dropping is genuinely acceptable (see the separate skill on `select` with
  `default` dropping messages).

## Verify
Run the previously-hanging code path under `go test -race -timeout 10s` (or
the specific reproduction with a hard timeout wrapped around it) enough times
to have previously reproduced the hang reliably, and confirm it now completes
well within the timeout on every run, plus inspect a goroutine dump taken
mid-run to confirm no two goroutines are blocked on each other's channel.
