---
name: threads-dont-speed-up-cpu-bound-python
description: Splitting a CPU-heavy Python computation across multiple threads produces no speedup, and sometimes runs slower than a single thread.
triggers: ["threading not faster python", "threadpoolexecutor no speedup", "multithreading slower than single thread", "python threads not parallel", "GIL blocking threads"]
permissions: ["READ"]
---

## Symptom
A CPU-bound Python workload (numeric computation in pure Python, string
processing, hashing, parsing) is split across multiple
`threading.Thread` instances or a `ThreadPoolExecutor` expecting it to
run faster proportional to the number of threads/cores, but total
wall-clock time stays roughly the same as running it on one thread -- or
gets measurably worse as more threads are added.

## Likely causes
1. **The Global Interpreter Lock (GIL) serializes execution of pure
   Python bytecode across threads.** Only one thread runs Python
   bytecode at a time regardless of how many CPU cores are available;
   threads give the *appearance* of concurrency (useful for I/O-bound
   work, where a thread waiting on I/O releases the GIL) but provide no
   real parallelism for CPU-bound Python code, which never voluntarily
   releases the GIL until the interpreter's periodic switch interval.
2. **Added threads increase GIL contention/switching overhead** without
   adding real throughput -- more threads means more context switches as
   the GIL bounces between them, which can make total wall-clock time
   *worse* than a single thread doing the same total work sequentially,
   especially on workloads with many small units of work.
3. **A mistaken assumption that a C-extension call releases the GIL.**
   Some operations (numpy vectorized operations, some regex/hashlib
   calls, I/O syscalls) do release the GIL during the C portion of their
   work, which can make threading genuinely help for *those specific
   calls* -- but if the actual hot loop is pure Python arithmetic or
   object manipulation wrapped around a C call, the GIL-releasing part
   is not where the time is going, so threading still doesn't help
   overall.

## Diagnose
- Confirm the workload is CPU-bound, not I/O-bound: profile it with
  `cProfile` or `py-spy` and check whether time is spent in Python-level
  loops/object creation versus blocked on `read`/`recv`/`connect` calls
  -- threading helps the latter, not the former.
  \
- Measure with an increasing thread count (1, 2, 4, 8) and plot total
  wall-clock time: a flat or *increasing* line as thread count grows
  (instead of decreasing toward the single-core-limited floor) is the
  direct signature of GIL-bound work; genuinely parallel work shows time
  decrease roughly proportional to added threads up to the core count.
- Use `py-spy dump` (or `sys._current_frames()` sampling) while the
  threaded run is in progress and check how many threads are actually
  executing Python bytecode at each sample versus how many are blocked
  waiting for the GIL -- for CPU-bound work, only one will ever be shown
  actively running.

## Fix
Use `multiprocessing` (or `concurrent.futures.ProcessPoolExecutor`)
instead of threads for CPU-bound work -- separate processes each get
their own Python interpreter and GIL, so they run truly in parallel
across cores. Reserve threads (`ThreadPoolExecutor`,
`asyncio.to_thread`) for I/O-bound work, where the GIL is released while
waiting on the OS. If the workload is a mix, split it: do I/O
concurrently with threads/async, and hand the CPU-heavy portion to a
process pool.

```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor() as pool:
    results = list(pool.map(cpu_heavy_fn, chunks))
```

For numeric workloads specifically, consider whether a vectorized
library (numpy, polars) that does the heavy lifting in C without holding
the GIL the whole time is a better fit than parallelizing Python-level
loops at all.

## Pitfalls
- Switching to `multiprocessing` naively for many small tasks can make
  things *slower* than threading due to per-task process-communication
  and (de)serialization overhead -- batch work into larger chunks per
  worker rather than submitting one process-pool task per tiny unit of
  work.
- Some libraries advertised as "GIL-releasing" only release it for a
  narrow portion of the call (e.g. the actual I/O syscall, not
  surrounding Python-level buffer handling) -- verify the specific
  function actually used releases the GIL for the expensive part, rather
  than assuming based on the library's general reputation.

## Verify
Re-run the thread-count scaling measurement (1, 2, 4, 8 workers) using a
process pool instead of a thread pool for the same CPU-bound workload,
on a machine with at least that many cores, and confirm wall-clock time
now decreases roughly proportionally as workers are added, up to the
core count -- contrasting with the flat/worsening curve seen with
threads.
