---
name: angular-switchmap-race-condition-search
description: Diagnose a search-as-you-type feature that displays results from an earlier keystroke instead of the latest one.
triggers: ["search results out of order angular", "switchmap vs mergemap race condition", "typeahead shows stale results", "wrong search results returned angular rxjs"]
permissions: ["READ"]
---

## Symptom
In a type-ahead or search-as-you-type feature, the displayed results
sometimes correspond to an earlier query rather than the one currently in
the input box -- most noticeable on a slow or throttled network, where a
fast typist sees results "snap back" to an earlier, wrong query.

## Likely causes
1. **Using `mergeMap` (or manually nesting `.subscribe()` calls) to chain
   the HTTP request off `valueChanges`**, which lets every keystroke's
   request run concurrently -- whichever response happens to land last
   wins, not whichever request was made last.
2. **Using `concatMap`**, which queues requests strictly in submission
   order and waits for each to finish before starting the next -- results
   arrive in correct order but visibly lag, since each waits for the
   queue to drain rather than cancelling stale, now-irrelevant requests.
3. **Missing `debounceTime`/`distinctUntilChanged` before the flattening
   operator**, causing a request to fire on every keystroke instead of
   after a typing pause, which multiplies however many in-flight requests
   whatever flattening operator is chosen has to contend with.
4. **The backend doesn't guarantee response ordering matches request
   ordering** even when the client cancels correctly, so a stale response
   already in flight when cancellation was requested can still arrive and
   needs to be recognized as stale, not just prevented from being sent.

## Diagnose
- Open the Network tab, type a fast multi-character query, and compare
  the order requests were *sent* against the order their responses
  *arrived* -- if a later request's response arrives before an earlier
  one, and the earlier one still overwrites the displayed results, that
  confirms the flattening operator is the problem.
- Grep the search pipeline for the RxJS operator chaining the HTTP call:
  `switchMap` unsubscribes from (and, for `HttpClient`, aborts) the
  previous inner request on every new source emission; `mergeMap` and
  `concatMap` do not cancel anything.
- Throttle the network to "Slow 3G" in DevTools and repeat the fast-typing
  test -- races invisible on localhost typically reproduce reliably under
  artificial latency.

## Fix
- Switch the flattening operator to `switchMap`, which cancels the
  previous inner observable every time the source emits a new search
  term -- exactly the "only the latest query matters" semantics a
  type-ahead needs.
- Add `debounceTime(250-300)` and `distinctUntilChanged()` upstream of the
  `switchMap` so requests only fire once typing pauses and duplicate
  consecutive terms don't re-trigger a fetch, shrinking the surface for
  any remaining race.
- If every keystroke's request must still produce some side effect (e.g.
  analytics logging) independent of what's displayed, keep a separate
  `mergeMap` pipeline for that side effect and drive only the *displayed*
  result through `switchMap`, since the two have genuinely different
  correctness requirements.

## Pitfalls
- Reflexively replacing every `mergeMap` in the codebase with `switchMap`
  breaks cases where concurrent, independent work is actually desired
  (e.g. submitting several unrelated uploads at once) -- `switchMap`'s
  cancellation is specifically right for "supersede the previous work,"
  not parallel independent work.
- Adding `debounceTime` without also fixing the flattening operator
  reduces how often the race triggers but doesn't eliminate it -- it's a
  mitigation, not a fix, and will still fail under bad-enough network
  conditions or fast-enough typing.

## Verify
Repeat the throttled-network fast-typing test: type a query, change it
again before the first request would have finished, and confirm only the
final query's results ever render, with the Network tab showing the
earlier request's status as cancelled rather than merely ignored.
