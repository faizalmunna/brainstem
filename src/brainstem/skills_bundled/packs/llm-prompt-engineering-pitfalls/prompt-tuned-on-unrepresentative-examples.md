---
name: prompt-tuned-on-unrepresentative-examples
description: A prompt performs well against the small hand-picked test set it was tuned on but fails noticeably on the actual diversity of real production inputs.
triggers: ["prompt worked great in testing but fails in production", "accuracy dropped once we shipped to real users", "our eval set didn't catch this failure mode", "prompt overfit to our test cases"]
permissions: ["READ"]
---

## Symptom
During development, a prompt is iterated against a handful of test cases (often 5-20, often written by the same person who wrote the prompt) and reaches what looks like reliable behavior. After shipping, the failure rate in production is substantially higher than testing suggested, and the failures often involve input variations -- different phrasing, length, language, formatting, or edge cases -- that simply weren't represented in the original test set.

## Likely causes
1. **The test set was authored by the prompt engineer, not sampled from real users** -- it reflects the author's mental model of the task and its edge cases, which systematically differs from the actual distribution of how real users phrase requests or what real input data looks like.
2. **Test set size too small to have statistical power** -- passing 15 out of 15 hand-picked examples says little about a production failure rate that only shows up at 1-in-200, especially if those 15 examples cluster around the common case.
3. **Iterating against the same fixed test set repeatedly causes implicit overfitting** -- each prompt tweak is kept if it improves that specific set, which optimizes for those exact examples' quirks rather than the general task, the same failure mode as overfitting a model to a validation set reused too many times.
4. **No negative/adversarial examples in the test set** -- only "should succeed" cases were tested, with no deliberately malformed, ambiguous, out-of-scope, or edge-case inputs that real production traffic inevitably contains.
5. **Missing input diversity along dimensions the author didn't think to vary** -- language, length, formatting (plain text vs. markdown vs. HTML-laden), or domain-specific jargon that wasn't part of the original test authoring context.

## Diagnose
- Pull a random (not cherry-picked) sample of actual production inputs from logs, at least 100-200 if volume allows, and run the current prompt against them, comparing the failure rate to what was observed on the original hand-built test set.
- Cluster production failures by characteristic (length, language, format, topic) and check whether the original test set had any representative examples in the failing clusters at all.
- Check the test set's provenance and size: was it written by the prompt author, sampled from real usage, or scraped from a spec document -- and how many examples, across how many distinct input shapes?
- Review whether the test set has been reused across many prompt iterations without ever being refreshed from new production data, which would explain overfitting to its specific quirks.

## Fix
Build the evaluation set primarily from real, randomly (or stratified-randomly) sampled production inputs rather than hand-authored cases, refreshing it periodically as production traffic evolves rather than treating it as fixed once collected. Size it for statistical relevance to the failure rate that matters (tens of examples can catch gross breakage; hundreds are needed to detect low-single-digit-percent regressions with any confidence), and deliberately include adversarial/edge-case/out-of-scope inputs, not just examples expected to succeed. Treat prompt iteration like model iteration: hold out a portion of the real-sampled set as a true held-out check that isn't used during active tuning, so improvements against the tuning set are validated against data the prompt wasn't directly optimized against.

## Pitfalls
Growing the test set only by appending whatever example just broke in production, one at a time, forever, without stratified sampling, eventually produces a test set that's mostly a museum of past bugs rather than a representative sample of the current input distribution -- useful as a regression suite, but not sufficient on its own to catch the next unrepresented failure mode.

## Verify
After a prompt change, report both the pass rate on the held-out real-sampled set and the pass rate on the regression suite of past known failures separately, and only ship if both hold -- then re-sample a fresh batch of live production inputs post-deployment and confirm the observed production failure rate matches what the held-out set predicted, within a reasonable margin.
