---
name: flame-graph-wide-shallow-misread-as-hot
description: A flame graph shows a wide section at one stack depth and it gets treated as a single hot function when it is actually many separate cheap calls.
triggers: ["flame graph is wide but I can't find one slow function", "misreading a flame graph", "wide bar in flame graph but each call is fast", "flame graph shows lots of small calls not one bottleneck"]
permissions: ["READ"]
---

## Symptom

A flame graph shows a visually prominent wide band at some stack depth,
and the natural reading -- "this is the hot path" -- leads someone to
dig into that specific function looking for an expensive operation.
They find the function itself is cheap and fast on every individual
call, with no obvious inefficiency, and conclude (incorrectly) that the
profiler must be misleading or the problem is unfindable.

## Likely causes

- **Width in a flame graph represents aggregate sample count/time
  across all invocations, not a single expensive call** -- a function
  called 100,000 times at 10 microseconds each produces the same total
  width as a function called once at 1 second, but the fix for each is
  completely different (batch/reduce call count vs. optimize one
  expensive operation).
  it.
- **Merged/aggregated stacks combine many different call sites into one
  visual frame** because they share a function name (e.g., a common
  utility, an ORM's row-mapping function, a logging call) even though
  they're invoked from many unrelated places in the code for unrelated
  reasons -- the width reflects the sum of all call sites, not one
  problem location.
- **The width is real but represents fixed per-call overhead multiplied
  by a very high call count** (e.g., serialization, a logging
  statement, a small validation check invoked on every item in a large
  collection) -- the fix is reducing call count or batching, and looking
  for "what's slow inside this one call" finds nothing because nothing
  is, individually.
- **Reading total (inclusive) width as if it were exclusive (self) time**
  for that frame, when most of the width actually belongs to children
  further up the stack rendered above it.

## Diagnose

1. Check the sample/call count for the wide frame, not just its width --
   most profilers report both; a very high call count with low per-call
   time confirms "many cheap calls," not "one expensive call."
2. Check whether the wide frame's *self* time (icicle/flame graphs
   usually distinguish this, often via a different color or a separate
   metric) is actually small relative to its total/inclusive time -- if
   self time is low, the width is inherited from children and the frame
   itself isn't the target.
3. If the profiler supports it, break down the wide frame by caller
   (who is calling this function, and how many times from each call
   site) rather than only by the callee -- this reveals whether the
   volume comes from one runaway caller (fixable by reducing calls from
   that site) or is spread evenly (a genuine per-item cost that needs
   batching at a higher level).
4. Calculate expected total cost: (call count) x (per-call time) and
   confirm it matches the frame's reported total time -- this confirms
   the "wide because frequent" explanation quantitatively rather than by
   eyeballing the graph.

## Fix

For a wide-but-cheap-per-call frame, the fix targets call volume, not
per-call efficiency: batch the operation (e.g., one bulk database call
instead of N individual calls, one serialization pass instead of N),
eliminate redundant calls (e.g., a value recomputed identically inside a
loop that could be hoisted out or memoized), or reduce the collection
size being iterated if the volume itself is avoidable. This is a
different fix category from optimizing a single genuinely slow function,
so correctly distinguishing the two (via call count and self time, not
visual width) determines which fix applies.

## Pitfalls

Don't try to "optimize" a wide-shallow frame by micro-optimizing the
function body when the call count is the real driver -- shaving
microseconds off a function called 500,000 times can still be
worthwhile, but the bigger win is almost always reducing how many times
it's called, and teams that skip straight to micro-optimization often
get a small win while missing a 10-100x reduction available from
batching. Also don't dismiss a wide-shallow pattern as "just overhead,
nothing to do" -- high call-count patterns are frequently the most
tractable wins in a profile precisely because they point at an
architectural fix (batching) rather than a hard algorithmic one.

## Verify

After batching or reducing call count, re-profile and confirm the
previously wide frame's total sample count/width has shrunk
proportionally to the reduction in call count, and confirm end-to-end
latency or throughput for the affected operation improved by an amount
consistent with that frame's original share of total time.
