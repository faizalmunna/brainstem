---
name: multiprocessing-pool-hangs-unpicklable-argument
description: A multiprocessing.Pool call hangs indefinitely or workers die silently because an argument passed to them cannot be pickled across the process boundary.
triggers: ["multiprocessing pool hangs", "pool.map never returns", "picklingerror in worker", "multiprocessing worker died silently", "process pool stuck forever"]
permissions: ["READ"]
---

## Symptom
A call like `pool.map(func, items)` or `pool.apply_async(func, args)`
either hangs forever with no output and no exception, or the worker
processes appear to start and then silently die, and the main process
never receives a result or a traceback for what went wrong.

## Likely causes
1. **An unpicklable object is passed as an argument or is part of a
   closure/bound method sent to the worker** -- open file handles,
   database connections, thread locks, generators, lambdas, local
   (nested) functions, or objects holding any of these as attributes all
   fail to pickle. On some platforms/versions the failure surfaces as a
   clear `PicklingError` in the main process before the job is even sent;
   on others (notably with certain start methods or when the error
   happens pickling the *result* on the worker side) the worker process
   dies and the parent just waits forever for a response that will never
   come.
2. **The target function itself is not picklable** -- an instance
   method, a lambda, or a function defined inside another function (a
   closure) can't be pickled by reference the way a module-level function
   can, because pickling a function sends its *name and module path*, not
   its code; if it can't be looked up by that path in the worker process,
   pickling fails.
3. **The *return value* fails to pickle**, not the input -- the call
   succeeds inside the worker, but sending the result back through the
   result queue fails, which can manifest as a hang because the parent's
   `get()` on the `AsyncResult` never completes and no exception
   propagates to the caller depending on Python version and pool
   implementation.

## Diagnose
- Before submitting to the pool, manually attempt
  `pickle.dumps(func)` and `pickle.dumps(args)` (and, separately,
  `pickle.dumps(expected_result_shape)` if reproducible) in the main
  process -- this reproduces the exact pickling failure synchronously,
  with a full traceback, instead of hanging inside the pool machinery.
- Check the worker's `maxtasksperchild`/logs and, if using
  `multiprocessing.get_context("spawn")` versus the platform default
  (`fork` on Linux, `spawn` on Windows/macOS), be aware that `fork`
  workers inherit already-open resources (which can look like it "works"
  under fork but hangs under spawn) -- test under `spawn` explicitly
  (`multiprocessing.get_context("spawn").Pool(...)`) since it surfaces
  pickling requirements that `fork` can silently paper over.
- Reduce to a single `apply()` (synchronous, not `apply_async`) call
  with one item outside of any surrounding timeout/retry logic --
  synchronous calls raise the underlying exception directly in the
  caller rather than requiring a separate `.get()` to retrieve it,
  which quickly confirms whether the hang is pickling-related versus a
  genuine deadlock in the worker's own logic.

## Fix
Make every object that crosses the process boundary -- function,
arguments, and return value -- plain, picklable data: module-level
functions (not lambdas or nested closures) as the pool target,
plain data structures (dicts, dataclasses without unpicklable fields,
primitives) as arguments and results, and open resources (files, DB
connections, sockets) created *inside* the worker function itself rather
than passed in from the parent. If a class method must be the unit of
work, use a module-level wrapper function that accepts serializable
identifying data (an ID, a config dict) and reconstructs whatever
resource it needs locally:

```python
# top-level, picklable
def process_item(item_id: int) -> dict:
    conn = get_connection()   # created inside the worker, not passed in
    try:
        return {"id": item_id, "result": conn.fetch(item_id)}
    finally:
        conn.close()

with multiprocessing.Pool(4) as pool:
    results = pool.map(process_item, item_ids)
```

## Pitfalls
- Switching to `dill` or another pickle-alternative to "fix" unpicklable
  closures papers over the design problem and reintroduces the same
  fragility later (new unpicklable attributes creep back in undetected)
  -- prefer passing plain data and reconstructing resources per-worker.
- Relying on `fork` start-method behavior (workers inheriting the
  parent's open resources/state) works on Linux but breaks on Windows
  and on macOS since Python 3.8's default switched to `spawn` -- code
  tested only on Linux under `fork` can appear correct in CI and then
  hang or error for every user on another platform.

## Verify
Force the pool to use the `spawn` start method explicitly in a test
(`multiprocessing.get_context("spawn").Pool(...)`), run the same
workload that previously hung under the default context, and confirm it
completes and returns correct results without hanging -- `spawn`
surfaces pickling issues that `fork` can mask, so passing under `spawn`
is a stronger signal the fix is real than passing under `fork` alone.
