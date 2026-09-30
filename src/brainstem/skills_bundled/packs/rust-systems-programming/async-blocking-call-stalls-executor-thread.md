---
name: async-blocking-call-stalls-executor-thread
description: Diagnose unrelated async tasks stalling or missing deadlines because a synchronous blocking call was made directly inside an async function.
triggers: ["tokio tasks not making progress", "async server latency spikes randomly", "blocking call in async fn", "tasks starved on same worker thread", "why is my async code not concurrent"]
permissions: ["READ"]
---

## Symptom
An async server or task pool experiences intermittent latency spikes or
apparent "freezes" where multiple unrelated requests/tasks stall at the same
time, even though they don't share any data or lock. Metrics often show one
worker thread pegged at 100% CPU (or blocked in a syscall) while others are
idle, and the stalls correlate with a specific endpoint or task type that
does file I/O, calls a synchronous library, or does CPU-heavy work. The code
compiles and looks correctly async (`async fn`, `.await` used elsewhere),
which makes it non-obvious that one specific call inside it is actually
synchronous and blocking.

## Likely causes
1. **A synchronous, blocking standard-library or third-party call is made
   directly inside an `async fn`** -- e.g. `std::fs::read`, `std::thread::sleep`,
   a synchronous database driver call, or a blocking HTTP client -- none of
   these yield control back to the executor; they block the OS thread the
   task happens to be running on, and every other task scheduled on that
   same worker thread (which async runtimes multiplex many tasks onto a
   small thread pool) is starved until the blocking call returns.
2. **CPU-bound work (parsing, hashing, image processing, serialization of a
   large payload) runs inline inside an async task** without ever hitting an
   `.await` -- there's nothing technically "blocking" in the I/O sense, but
   the task monopolizes its worker thread for the whole computation, which
   has the same starving effect on cooperatively-scheduled sibling tasks.
3. **A `Mutex` from `std::sync` (not the async-aware `tokio::sync::Mutex`)
   is locked inside async code and held across meaningful work** -- while
   waiting to acquire it, the executor thread blocks synchronously rather
   than yielding, so contention on that lock also starves unrelated tasks
   on the same thread even though the lock itself has nothing to do with
   them.
4. **A blocking call is hidden inside a library's "async-looking" API** --
   some crates offer `async fn` wrappers that internally still shell out to
   a blocking C library or do blocking DNS resolution, so the blocking
   happens even though the call site itself looks properly async.

## Diagnose
- Check the runtime's worker thread count vs. observed concurrency: if
  `tokio::main` uses the default multi-threaded scheduler with N worker
  threads, and stalls affect roughly 1/N of concurrent requests at a time
  in a pattern that lines up with one thread being busy, that's a strong
  signal of thread starvation rather than a lock or I/O-target issue.
- Use `tokio-console` (the `console-subscriber` crate) against the running
  process -- it directly shows tasks with abnormally long "poll" durations,
  which is the precise signature of a task that blocked its thread instead
  of yielding; a task with a multi-millisecond-or-longer single poll is
  the culprit.
- Grep the async code paths for direct use of `std::fs::*`, `std::thread::sleep`,
  `std::sync::Mutex`/`RwLock`, or any client library not explicitly marked
  async (check its docs/crate name -- e.g. `reqwest::blocking::Client` vs.
  `reqwest::Client`) -- these are the concrete call sites to inspect first.
  rather than guessing.
- Reproduce under load with `perf top` or `htop` per-thread view while
  hitting the suspect endpoint -- a worker thread showing sustained 100% in
  a syscall (`read`, `futex`) or in application code with no `.await` in
  between confirms a blocking call is monopolizing that thread.

## Fix
Move blocking or CPU-heavy work off the async executor's worker threads
entirely, using the runtime's dedicated blocking-task mechanism, and hand
the result back via a channel or the task's return value:
```rust
// Bad: blocks whichever worker thread happens to run this task.
async fn handler() -> Result<Vec<u8>> {
    let data = std::fs::read("large_file.bin")?; // blocking syscall
    Ok(data)
}

// Good: runs on tokio's dedicated blocking thread pool instead.
async fn handler() -> Result<Vec<u8>> {
    let data = tokio::task::spawn_blocking(|| std::fs::read("large_file.bin"))
        .await??;
    Ok(data)
}
```
For CPU-bound work with no I/O at all, the same `spawn_blocking` pattern
applies (it's not just for I/O -- it's for anything that won't yield on its
own), or use `rayon` for data-parallel CPU work and bridge the result back
with a channel. Replace `std::sync::Mutex`/`RwLock` used inside async code
paths with the runtime's async-aware equivalents (`tokio::sync::Mutex`) only
where the critical section itself needs to be held across an `.await`;
otherwise a `std::sync::Mutex` held only across quick, non-yielding
synchronous work is fine and often faster -- the problem is specifically
blocking *while other tasks need the thread*, not the primitive itself.

## Pitfalls
- Using `spawn_blocking` for something that's actually cheap and
  non-blocking -- it has real overhead (moving work to a separate thread
  pool, channel synchronization for the result) and defaults to a bounded
  pool size, so overusing it for trivial work can itself become a
  bottleneck or exhaust the blocking pool under load.
- Switching to `tokio::sync::Mutex` everywhere reflexively "to be safe in
  async code" -- it's slower than `std::sync::Mutex` for short critical
  sections and only actually helps when the guard must be held across an
  `.await`; using it as a blanket replacement adds overhead without fixing
  anything if nothing was actually blocking.
- Wrapping the blocking call in `spawn_blocking` but then `.await`-ing it
  immediately in a tight loop per-item instead of batching -- this pays the
  cross-thread handoff cost per item and can be slower than a single
  batched blocking call for many small items.

## Verify
Re-run the same `tokio-console` session (or the per-thread `perf`/`htop`
observation) under the load pattern that originally showed starvation and
confirm poll durations for the previously-blocking task drop to sub-
millisecond, and that sibling tasks on the same worker no longer show
latency spikes correlated with it. Add a load test that runs the
previously-blocking endpoint concurrently with a latency-sensitive endpoint
and assert the latter's p99 latency stays flat regardless of load on the
former.
