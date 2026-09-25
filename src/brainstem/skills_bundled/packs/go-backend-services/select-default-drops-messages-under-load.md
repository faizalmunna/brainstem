---
name: select-default-drops-messages-under-load
description: Diagnose silently missing messages or events in a channel-based pipeline caused by a select statement's default case discarding sends whenever the channel isn't immediately ready.
triggers: ["messages silently dropped under load", "select default case eating events", "channel send skipped silently", "metrics missing under high traffic", "non-blocking send losing data"]
permissions: ["READ"]
---

## Symptom
Under light load, everything works: events, metrics, or messages sent on a
channel all seem to arrive at their consumer. Under heavier concurrent load,
a fraction of them silently go missing with no error, no log line, no panic
-- just a gap in the data (missing metric points, missing log entries,
missing processed items) that's easy to miss unless something downstream
specifically counts for completeness.

## Likely causes
1. **A `select` with a `default` case is used for a non-blocking send that
   was intended as an optimization ("don't block the hot path"), but the
   `default` branch silently discards the value instead of logging,
   counting, or otherwise surfacing the drop** -- functionally correct in
   the sense that it doesn't block, but the drop itself is invisible.
2. **The channel's buffer size was sized for average load, not peak/burst
   load**, so under a traffic spike the buffer fills, sends stop succeeding
   immediately, and the `default` branch starts firing exactly when the data
   matters most (a spike is often the interesting event to capture).
3. **The consumer goroutine is itself slow or stalled** (blocked on a
   downstream call, GC pause, lock contention) so it's not draining the
   channel at the rate producers assume, making the buffer-full condition
   trigger even under otherwise-normal producer load.
4. **A misunderstanding of intent**: `select`/`default` was copied from an
   example that genuinely wanted best-effort/lossy delivery (e.g. sampling),
   but applied to a code path where every item actually needs to be
   delivered (e.g. billing events, audit logs) -- the pattern itself isn't
   wrong, it's wrong for this particular data.

## Diagnose
- Grep for `select {` blocks with a `case ch <- v:` paired with `default:`
  -- each one is a candidate; the question is whether dropping is
  acceptable for that specific channel's data.
- Add a counter (even a simple `atomic.Int64`) incremented in the `default`
  branch, and expose it via existing metrics/logging -- run under production-
  like load and check whether this counter is nonzero, which proves drops
  are happening and roughly how often.
- Check the channel's buffer size (`make(chan T, N)`) against the actual
  peak production rate vs. consumer drain rate -- compute or measure both
  under load rather than guessing.
- Profile the consumer goroutine during a suspected drop window (pprof CPU
  profile, or simply logging timestamps in the consume loop) to see whether
  it's actually keeping up or itself stalled, which changes whether the fix
  is "buffer more" or "fix the consumer."

## Fix
First decide, explicitly, whether this data can tolerate loss -- if yes
(e.g. best-effort metrics sampling), keep the non-blocking send but make the
drop observable:
```go
select {
case ch <- v:
case default:
    droppedCounter.Add(1) // now visible in metrics instead of silent
}
```
If the data must not be lost, remove the `default` case and let the send
block, applying backpressure to the producer -- combined with a context so
the producer can still abort on cancellation rather than block forever:
```go
select {
case ch <- v:
case <-ctx.Done():
    return ctx.Err()
}
```
If blocking the producer is unacceptable but loss also is not, use a properly
sized buffered channel plus a separate overflow strategy (spill to disk, a
secondary durable queue, or explicit backpressure signaling to the caller)
rather than a bare `default` that discards -- the right answer depends on
what the system can afford, but it should be a deliberate choice, not a
side effect of copy-pasted non-blocking-send code.

## Pitfalls
- Simply enlarging the channel buffer to "fix" the drops without adding
  observability just delays the point where drops become visible again under
  a bigger spike -- always pair a buffer size decision with monitoring of how
  full the buffer actually gets in production.
- Removing `default` everywhere reflexively turns every send into a
  potentially-blocking one, which can create backpressure that cascades
  upstream (a slow consumer now stalls producers, which stalls their
  callers) -- confirm the whole chain can tolerate blocking before removing
  a non-blocking send wholesale.
- Counting drops but never alerting on the counter leaves the visibility fix
  incomplete -- a metric nobody looks at is barely better than no metric.

## Verify
Load-test the pipeline at a rate that previously produced silent drops, with
the drop counter wired to metrics, and confirm either (a) the counter stays
at zero after switching to a blocking send with proper backpressure, or (b)
for an intentionally-lossy path, that the counter accurately reflects actual
drops and downstream consumers/dashboards account for the sampling rate
rather than assuming complete data.
