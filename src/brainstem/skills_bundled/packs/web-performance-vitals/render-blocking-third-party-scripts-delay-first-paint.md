---
name: render-blocking-third-party-scripts-delay-first-paint
description: Fix a delayed first paint caused by third-party scripts like chat widgets or analytics loaded synchronously in the document head.
triggers: ["first paint is delayed", "render blocking script warning", "chat widget slows page load", "third party script blocking render", "FCP delayed by script tag"]
permissions: ["READ"]
---

## Symptom
Lighthouse flags "Eliminate render-blocking resources" or "Reduce the
impact of third-party code," and the page shows a blank or unstyled screen
for longer than expected before First Contentful Paint, even though the
page's own HTML/CSS is lightweight -- the delay tracks specifically with
scripts from other domains (chat widgets, A/B testing tools, analytics
SDKs, tag managers).

## Likely causes
1. **A `<script src="...">` tag with no `async`/`defer` sits in `<head>`**
   before the page's own CSS/content, so the browser must download and
   execute it (a network round-trip to a third-party server) before it can
   continue parsing the rest of the document.
2. **A third-party script is loaded synchronously specifically because it
   needs to run before content renders** (e.g. an A/B testing tool that
   must apply a variant before paint to avoid a "flicker" of the wrong
   variant), which is a real constraint but is being solved with a
   blocking full library load instead of a minimal inline snippet.
3. **Multiple third-party scripts are chained** -- a tag manager loads,
   which then loads several more scripts sequentially, multiplying the
   blocking delay by the number of hops instead of loading them in
   parallel.
4. **The third-party server itself is slow or geographically distant**,
   so even a correctly-async script delays *something* the user is waiting
   on (e.g. it's async but the page's own logic waits on a callback from
   it before proceeding).

## Diagnose
- In DevTools > Network, sort by start time and look for third-party
  domains whose requests appear before the page's own CSS/critical JS
  finishes, and check whether they have `async`/`defer` attributes via
  Elements panel.
- Use DevTools > Performance and look at the "Main" thread track before
  First Paint -- a long "Evaluate Script" block attributed to a
  third-party URL right before the paint marker confirms it's blocking.
- Run Lighthouse's "Third-party usage" and "Reduce impact of third-party
  code" audits, which specifically attribute main-thread blocking time
  and transfer size to each third-party origin.
- Temporarily block the suspect script's domain via DevTools > Network
  request blocking and reload to measure FCP with/without it, isolating
  its actual contribution versus assumption.

## Fix
Give the browser permission to keep parsing and painting the page's own
content while third-party code loads, and reserve synchronous loading only
for the rare case where a script must genuinely run before paint (and even
then, keep that synchronous part minimal). Concretely: add `async` (loads
in parallel, executes as soon as ready, order not guaranteed) or `defer`
(loads in parallel, executes in order after parsing, before
`DOMContentLoaded`) to third-party script tags so they no longer block
HTML parsing; load tag managers and their downstream scripts via the
async pattern the vendor provides, and audit what's actually configured
to fire on page load versus what could fire later/on interaction; for
scripts that must prevent visual flicker (A/B test variant application),
inline only the minimal snippet needed to make that decision synchronously
and load the rest of the library asynchronously; and move genuinely
non-critical third-party code (chat widgets, feedback buttons) to load
after the page is interactive, e.g. on a `requestIdleCallback` or after a
short delay/first user interaction.

## Pitfalls
- Switching every script to `async` without checking execution-order
  dependencies (e.g. a script that assumes a global variable set by an
  earlier script) can break functionality silently -- verify order-
  sensitive scripts still work, or use `defer` where order matters.
- Delaying analytics/tracking scripts too aggressively can undercount
  bounces (users who leave before the delayed script ever fires) --
  balance performance against data completeness for scripts whose whole
  job is measuring the visit.
- Removing a synchronous A/B testing script for performance without
  another fix can reintroduce the flicker it was preventing -- address
  the actual constraint, don't just delete the blocking behavior.

## Verify
Re-run Lighthouse and confirm the "render-blocking resources" audit no
longer lists the third-party script, that FCP/LCP timing improved in the
lab report, and check real-user field data (CrUX) for the page over the
following days to confirm the improvement holds across the actual device/
network mix of visitors.
