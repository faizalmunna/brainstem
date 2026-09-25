---
name: gather-return-exceptions-swallowed
description: One task inside an asyncio.gather batch fails but the failure never surfaces because return_exceptions=True was used without checking the results for exception objects.
triggers: ["gather return_exceptions swallowed error", "asyncio gather silent failure", "one task failed but gather succeeded", "return_exceptions true hides error", "gather results contain exception not raised"]
permissions: ["READ"]
---

## Symptom
`asyncio.gather(*coros, return_exceptions=True)` is used so that one
failing coroutine doesn't cancel the others, and the call "succeeds" --
it returns a list without raising. Downstream code processes the
results as if they were all successful values, and a failure that
actually occurred (a `None` written to a database field, a broken
report row, a metric silently missing) is only discovered much later, if
at all, because nothing ever inspected the results for exception
objects mixed into the list.

## Likely causes
1. **`return_exceptions=True` was added specifically to stop one
   failure from cancelling the whole batch, without also adding the
   corresponding check.** `gather` with this flag returns a list where
   failed coroutines contribute their *exception instance* in place of a
   normal return value, instead of raising -- the caller must explicitly
   iterate the results and check `isinstance(r, BaseException)` for
   each one; there's no automatic signal that any element is actually an
   error.
2. **Results are passed directly into code expecting uniform, valid
   data** -- e.g. `zip`ped with the original inputs and inserted into a
   database, or summed/aggregated -- so an exception object flows into
   logic that doesn't type-check it, often failing later with a
   confusing, unrelated-looking `TypeError` (or, worse, being coerced
   into something like a string and stored without erroring at all).
3. **Partial success is treated as full success at a higher layer** --
   e.g. a batch job logs "processed N items" using `len(results)`
   without subtracting how many of those results were actually
   exceptions, so monitoring/alerting never reflects the real failure
   rate.

## Diagnose
- Grep for `return_exceptions=True` and, at every call site, check
  whether the code immediately after iterates the returned list looking
  for exception instances -- if the next line just indexes into or maps
  over the results directly, that's the gap.
- Reproduce by including one coroutine in the batch that deliberately
  raises, run the `gather` call, and print `[type(r) for r in results]`
  -- confirm the failing coroutine's slot holds an exception type rather
  than crashing the whole call, then trace where that list is consumed
  next to see whether anything downstream would notice.
- Check monitoring/logging around the batch operation for a metric that
  distinguishes "items attempted" from "items that raised" -- if the
  only metric is a total count or a boolean "batch succeeded," partial
  failures are structurally invisible in current observability.

## Fix
Immediately after any `gather(..., return_exceptions=True)` call,
separate successes from failures explicitly and decide what to do with
each -- log/report the failures, and only pass genuine successes
downstream:

```python
results = await asyncio.gather(*coros, return_exceptions=True)

successes, failures = [], []
for item, result in zip(inputs, results):
    if isinstance(result, BaseException):
        failures.append((item, result))
    else:
        successes.append(result)

if failures:
    logger.error("gather: %d/%d failed", len(failures), len(results))
    for item, exc in failures:
        logger.error("failed for %r", item, exc_info=exc)

process(successes)   # never feed raw `results` downstream unchecked
```

If any failure should actually abort the whole operation rather than
being tolerated, re-raise one of the collected exceptions (or a
combined `ExceptionGroup` via `asyncio.TaskGroup` on Python 3.11+, which
surfaces multiple concurrent failures together instead of picking one
arbitrarily) rather than continuing silently.

## Pitfalls
- Checking only `if failures: logger.error(...)` without re-raising or
  otherwise failing the operation can turn a real outage into a
  permanently "successful-looking" job that just quietly drops a
  fraction of its work every run -- decide deliberately, per call site,
  whether partial failure should be tolerated-and-reported or should
  still fail the overall operation.
- On Python 3.11+, `asyncio.TaskGroup` raises an `ExceptionGroup`
  containing *all* concurrent failures if one task fails (and cancels
  the rest by default), which is a different tradeoff than
  `return_exceptions=True` -- don't reach for `TaskGroup` assuming it
  gives you "gather but automatically checked," since its default is to
  cancel siblings on first failure rather than let them all finish.

## Verify
Add a coroutine to the batch that deliberately raises a distinct,
recognizable exception, run the fixed code, and confirm: the failure is
logged with enough detail to identify which input caused it, the
successful items still get processed, and the batch's reported
success/failure counts in logs or metrics reflect the actual 1-failure
result rather than reporting the batch as fully successful.
