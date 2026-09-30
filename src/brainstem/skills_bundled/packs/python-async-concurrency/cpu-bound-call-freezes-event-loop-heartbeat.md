---
name: cpu-bound-call-freezes-event-loop-heartbeat
description: An entire asyncio application stops responding to anything -- timers, other coroutines, even signals -- for the duration of one CPU-heavy computation.
triggers: ["event loop frozen", "asyncio app hangs during computation", "timers stop firing during heavy work", "bot stops responding while processing", "event loop not responsive"]
permissions: ["READ"]
---

## Symptom
An asyncio-based application (a bot, a scheduler, a WebSocket server, a
long-running worker -- not necessarily an HTTP API under load) goes
completely unresponsive whenever it runs a particular computation:
scheduled callbacks don't fire on time, other coroutines that should be
running concurrently make no progress, heartbeats/keepalives to peers go
silent, and sometimes even `Ctrl-C` doesn't interrupt the process
promptly. Everything resumes normally once the computation finishes.

## Likely causes
1. **A genuinely CPU-bound computation (parsing, hashing, image/array
   processing, a tight Python loop) is executed directly inside a
   coroutine** with no `await` inside it. The event loop is
   single-threaded and cooperative: it only switches to another
   coroutine at an `await` point, so a long synchronous stretch of code
   holds the loop hostage for its entire duration, regardless of how
   many other tasks are scheduled.
2. **A "fast enough in testing" computation is fed production-sized
   input.** A function that takes 2ms on a test fixture but 2 seconds on
   a real payload was never actually fixed -- it was just too fast to
   notice the loop was blocked. This differs from a chronically slow
   handler: the freeze is intermittent and input-size-dependent.
3. **A library call assumed to be non-blocking is actually synchronous
   internally** -- e.g. a "compression" or "serialization" helper that
   looks like a quick utility call but does non-trivial CPU work
   (compressing a large payload, deep-copying a large structure) with no
   `await`, so it's missed in code review because it doesn't look like
   the classic "CPU-bound" example.

## Diagnose
- Run with asyncio's debug mode and a slow-callback threshold:
  `asyncio.run(main(), debug=True)` with
  `loop.slow_callback_duration = 0.1` (or set
  `PYTHONASYNCIODEBUG=1`) -- the loop logs a warning naming the exact
  callback/coroutine step that took too long, which points directly at
  the offending code instead of requiring manual bisection.
- Add a lightweight heartbeat coroutine (`while True: print(time.time());
  await asyncio.sleep(0.5)`) running alongside the suspect code; a gap
  in its timestamps larger than the sleep interval proves the loop was
  blocked and for how long, correlated with what else was running at
  that moment.
- Profile the suspect function in isolation with `cProfile` or
  `time.perf_counter()` around it to get an actual duration, then
  compare that duration to the observed freeze length -- if they match,
  the function itself is the blocking span, not something it calls out
  to.

## Fix
Move CPU-bound work off the event loop thread entirely rather than
trying to make it "more async." For work that's CPU-bound (as opposed to
I/O-bound), use `loop.run_in_executor(process_pool, func, *args)` with a
`concurrent.futures.ProcessPoolExecutor` so the computation runs in a
separate process and doesn't contend with the event loop thread or the
GIL at all; `await` the resulting future so the coroutine yields control
back to the loop while the process pool does the work. For something
merely inconvenient rather than genuinely CPU-heavy, `asyncio.to_thread`
is enough, but it will not speed up pure-Python CPU-bound work because
of the GIL -- only true parallelism (process pool) or breaking the work
into smaller `await`-separated chunks avoids the freeze for a strictly
CPU-bound job.

## Pitfalls
- Reaching for `asyncio.to_thread` for CPU-bound work "fixes" the freeze
  the same way a process pool does (the loop stops blocking) but doesn't
  make the computation itself faster and can still cause thread
  contention if many CPU-bound jobs pile up on the default executor's
  thread pool -- see the GIL-related skill in this pack for why that
  doesn't parallelize.
- Passing large objects to a `ProcessPoolExecutor` incurs real
  pickling/unpickling cost across the process boundary -- for very large
  payloads this overhead can rival or exceed the computation itself, so
  measure before assuming a process pool is free.

## Verify
Run the heartbeat-coroutine test again after the fix: the heartbeat's
timestamps should stay evenly spaced (no gap larger than the sleep
interval) even while the formerly-blocking computation is running,
confirming the event loop kept servicing other coroutines throughout.
