---
name: vue-watcheffect-unexpected-runs
description: Diagnose a watchEffect callback that fires far more or fewer times than the actual number of relevant state changes.
triggers: ["watchEffect running too many times", "watchEffect not firing", "watcher fires too often vue", "watchEffect infinite loop", "watch dependency not tracked"]
permissions: ["READ"]
---

## Symptom
A `watchEffect` callback either spams the console/network far more often
than the user's actions should cause, or silently fails to run again when
a value it clearly depends on changes -- often after adding an `await` or
refactoring the effect body.

## Likely causes
1. **`watchEffect` auto-tracks every reactive property read synchronously
   during its run**, including ones you didn't mean to depend on --
   reading a whole reactive object (or spreading it) pulls in every
   nested property as a dependency, so any unrelated change on that object
   re-triggers the effect.
2. **Dependencies read after an `await`** inside the effect aren't
   tracked at all -- Vue can only collect dependencies during the
   synchronous portion of the function's first pass, so a value read only
   in the `.then()`/post-`await` continuation silently fails to trigger
   future re-runs.
3. **The effect both reads and writes the same reactive value**, creating
   a feedback loop or at least an extra, easily-missed re-run each time it
   sets state that it also depends on.
4. **Misreading the default `flush: 'pre'` timing** as a bug -- the effect
   runs before the DOM updates, so code that reads DOM state (`el.
   offsetHeight`) inside it sees stale layout and appears to "need" an
   extra run that `flush: 'post'` would have avoided.

## Diagnose
- Add the built-in dev-only debug hook: `watchEffect(fn, { onTrigger(e) {
  console.log(e) } })` -- it prints exactly which reactive property/target
  caused each re-run, which is far more precise than guessing from log
  spam.
- For missed re-runs, check whether the value in question is read before
  or after the first `await` in the effect body.
- Count invocations with a simple counter and compare against the number
  of relevant state changes made in a controlled manual test, rather than
  eyeballing console noise.

## Fix
When you want control over exactly which values matter, switch to
`watch(source, callback)` with an explicit source (or array of sources)
instead of relying on `watchEffect`'s implicit auto-tracking -- this
prevents unrelated nested changes on a large object from triggering it.
For the async-dependency-missed case, read every reactive value the
effect needs into local constants before the first `await`, so they're
captured as dependencies during the synchronous tracking phase. Use `{
flush: 'post' }` explicitly when the effect needs to read the
already-updated DOM.

## Pitfalls
Converting every `watchEffect` to `watch` with a long, manually-maintained
dependency array to silence noise treats the symptom, not the design
smell -- if one watcher is reacting to many unrelated pieces of state,
split it into several focused watchers instead of just narrowing the
tracking on one overloaded effect.

## Verify
With the `onTrigger` debug callback still attached in development, perform
a scripted sequence of state changes and confirm the number and source of
triggered runs matches exactly what you'd expect from that sequence --
neither extra runs from unrelated properties nor missing runs from
values read after an `await`.
