---
name: playwright-trace-debugging
description: Efficiently triage a failing Playwright test using the trace viewer, screenshots, and video instead of guessing from the error message alone.
triggers: ["debug playwright test failure", "trace viewer", "playwright test failed why", "cant reproduce ci failure locally", "playwright show-trace"]
permissions: ["READ"]
---

## Symptom
A Playwright test fails (especially in CI, where it can't be watched
live) and the raw error message/stack trace alone isn't enough to
understand what actually went wrong on the page at the time of failure.

## Likely causes
This is a triage-methodology skill, not a single-cause bug -- the
underlying problem is usually **not collecting enough evidence at
failure time** to diagnose without reproducing manually, which is often
slow or impossible for CI-only or environment-specific failures.

## Diagnose
Systematically work through the artifacts, richest first:
1. **Trace file** (`--trace on` or `retain-on-failure`): open with
   `npx playwright show-trace trace.zip` to get a full timeline --
   every action, network request/response, console log, and a DOM
   snapshot at each step, scrubbable like a video but inspectable like a
   debugger.
2. **Screenshot at failure** (`screenshot: 'only-on-failure'`): the exact
   visual state when the assertion/action failed -- check for an
   unexpected overlay, an error toast, a loading spinner still visible, or
   a completely different page than expected.
3. **Video recording** (`video: 'retain-on-failure'`): useful for timing-
   sensitive issues where seeing the sequence of visual changes leading
   up to failure matters more than a single frame.
4. **Console and network logs captured in the trace**: check for a
   JavaScript error, a failed/slow network request, or an unexpected
   response that explains the state seen in the screenshot.

## Fix
- Configure the suite to always retain traces/screenshots/video on
  failure (not just locally, but in CI, since CI-only failures are the
  ones hardest to reproduce by hand) -- the cost is some CI artifact
  storage, which is worth it against debugging time saved.
- When triaging, start from the trace viewer's timeline and work
  backwards from the failed action/assertion to the last known-good
  state, rather than starting from the error message and guessing.
- Cross-reference the network tab within the trace against application
  logs/APM for the same time window when the failure involves backend
  behavior, not just frontend state.
- Once the root cause is identified from the trace, write the actual fix
  addressing that cause (a race condition, a locator issue, a real app
  bug) using the appropriate other skill in this pack rather than
  patching based on a guess.

## Pitfalls
- Retaining traces/video for *every* run (not just failures) in CI can
  consume significant storage/time for large suites -- `retain-on-failure`
  (or `on-first-retry`) is usually the right default, with `on` reserved
  for actively debugging a specific flaky test.
- Looking only at the final failure screenshot without checking the
  trace's action timeline can miss that the *real* problem happened
  several steps earlier (e.g. a login that silently failed, leaving the
  test proceeding in a logged-out state until a much later assertion
  finally fails).

## Verify
After identifying and fixing the root cause via trace inspection,
re-run the test with tracing still enabled and confirm the new trace
shows the previously-problematic step now completing as expected, not
just that the test passed.
