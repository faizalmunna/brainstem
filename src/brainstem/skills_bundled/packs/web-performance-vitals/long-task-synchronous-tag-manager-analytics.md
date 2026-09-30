---
name: long-task-synchronous-tag-manager-analytics
description: Fix a long task that blocks the main thread right after page load because a tag manager or analytics snippet runs a large amount of synchronous setup work.
triggers: ["long task warning on load", "google tag manager slows page", "analytics script blocks main thread", "page unresponsive right after load", "TBT caused by analytics"]
permissions: ["READ"]
---

## Symptom
For a second or two immediately after the page finishes loading, the page
is unresponsive to clicks/taps/scrolling even though nothing looks like
it's still loading visually -- Lighthouse flags one or more "long tasks"
(>50ms, often several hundred ms) attributed to a tag manager container or
analytics vendor script, and this specifically happens right at/after
load rather than in response to a user interaction (distinct from the
INP-heavy-handler skill, which is interaction-triggered).

## Likely causes
1. **A tag manager container fires many tags synchronously on page load**
   (multiple analytics pixels, remarketing tags, heatmap/session-recording
   scripts, A/B testing SDKs) that each do their own DOM scanning,
   cookie reads, or network calls in sequence.
2. **A single analytics/monitoring SDK does expensive synchronous
   initialization** -- scanning the entire DOM for elements to instrument,
   setting up many event listeners, or computing a device/session
   fingerprint synchronously.
3. **The tag manager itself loads and evaluates before the page's own
   critical scripts**, competing for the same main-thread time slice
   during an already-busy load sequence.
4. **Session-recording/heatmap tools serialize significant DOM state**
   (or attach mutation observers across the whole document) as part of
   their startup, which is inherently more expensive than a simple pixel
   fire.

## Diagnose
- In DevTools > Performance, record a page load and find the long task(s)
  in the main thread flame chart (marked with a red corner flag);
  expand the call stack to identify which script/vendor function is
  responsible.
- Use Lighthouse's "Minimize main-thread work" and "Reduce the impact of
  third-party code" audits, which attribute blocking time to specific
  third-party origins/scripts by name.
- In the tag manager's own debug/preview mode (e.g. GTM Preview), check
  how many tags fire on the "Page Load" / "DOM Ready" triggers versus how
  many could be deferred to a later or user-initiated trigger.
- Check whether disabling one suspect tag/script at a time (via the tag
  manager's debug console or DevTools request blocking) removes the long
  task, to isolate which specific tag is the actual culprit versus the
  container itself.

## Fix
Reduce how much synchronous setup work runs in the critical window right
after load, by moving non-essential tags to fire later and making sure
genuinely necessary ones don't all compete for the main thread at once.
Concretely: in the tag manager, change triggers for non-critical tags
(remarketing, heatmaps, most third-party pixels) from "Page Load"/"DOM
Ready" to a delayed trigger (a timer, `requestIdleCallback`, or "on first
user interaction") so they don't compete with content becoming
interactive; audit and remove tags that are no longer used or duplicate
functionality already covered by another tag (tag sprawl accumulates over
time as tools are swapped without cleanup); and where a vendor SDK
supports it, use its lightweight/async initialization mode instead of the
full synchronous SDK if only basic pageview tracking is needed.

## Pitfalls
- Deferring analytics tags too long can miss short-duration visits
  (bounces) entirely, undercounting real traffic -- there's a genuine
  tradeoff between performance and data completeness, not a free win;
  fire at least a minimal pageview beacon early and defer only the
  heavier instrumentation.
- Removing tags without checking with the marketing/analytics team first
  can silently break attribution/reporting they depend on -- audit tag
  purpose and ownership before deleting, don't unilaterally prune.
- Fixing the tag manager's own tags but ignoring that the tag manager
  container script itself is also large and synchronous leaves some of
  the long task in place -- check both the container and its child tags.

## Verify
Re-run Lighthouse and confirm the specific long task(s) previously
attributed to the tag manager/analytics origin no longer appear (or
shrank materially) in the "Reduce the impact of third-party code" audit,
and manually test that the page responds to a click/tap immediately after
load completes rather than after a noticeable freeze.
