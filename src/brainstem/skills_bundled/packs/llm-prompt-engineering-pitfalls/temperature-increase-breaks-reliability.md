---
name: temperature-increase-breaks-reliability
description: A prompt reliable at low temperature becomes inconsistent or breaks formatting once temperature is raised for a creative use case, without other adjustments.
triggers: ["raised temperature and now output is unreliable", "creative mode breaks our json output", "higher temperature causes format errors", "output quality degraded after increasing randomness"]
permissions: ["READ"]
---

## Symptom
A prompt tuned and validated at low temperature (near-deterministic output) is reused for a new feature that wants more creative/varied output, so temperature is raised -- and previously reliable behaviors that weren't the target of the change also degrade: JSON formatting breaks more often, instructions get followed less consistently, or factual claims become less reliable, alongside the intended increase in creative variation.

## Likely causes
1. **Temperature affects the entire output, not just the "creative" portion** -- there's no mechanism to apply high randomness only to the subjective/creative parts of a response while keeping structural elements (JSON keys, required fields, format markers) deterministic, so raising it globally trades off reliability everywhere at once.
2. **The prompt's instruction-following margin was already thin at low temperature** -- it worked reliably specifically because low temperature suppressed the model's tendency to occasionally deviate, masking an underlying fragility in the instructions themselves that becomes visible once sampling variance increases.
3. **No compensating structural safeguards were added alongside the temperature change** -- the prompt and pipeline were designed and tested under an implicit "low temperature" assumption (e.g. no output validation, no retry logic), and that assumption silently broke when temperature changed without revisiting those design decisions.
4. **Format-critical and creative-content generation are conflated in a single call** -- one prompt is asked to both produce free-form creative text and emit strict structural elements (JSON wrapper, required metadata fields) in the same generation pass, so there's no way to tune randomness differently for each part.
5. **Temperature was changed without re-running the evaluation/regression suite**, since the mental model was "this only affects creativity," not "this affects every aspect of sampling including format adherence."

## Diagnose
- Run the same test set used to validate the original low-temperature prompt at the new higher temperature and compare failure rates specifically on format/instruction-following criteria, isolated from the intended creative-quality metric.
- Check whether structural output (JSON, required fields, delimiters) is generated in the same model call as the creative content, or whether they could be separated into distinct calls/steps with independent temperature settings.
- Test a range of temperature values (not just the old and new endpoints) to see whether reliability degrades gradually or has a sharper breakpoint, which indicates how much margin exists before the intended creative use case is even usable.
- Check whether any output-side validation or retry logic exists at all -- if the pipeline was built assuming near-deterministic success, this is likely the missing safeguard now that failure rate has gone up.

## Fix
Separate structural/format generation from creative-content generation where possible -- use a lower temperature (or structured-output enforcement) for the call or portion that must produce reliable structure, and reserve higher temperature for the call or portion that benefits from variation, rather than one setting applied uniformly to a mixed-purpose prompt. Add output-side validation and a bounded retry (re-generate on format failure) as a safety net for the higher-temperature path, since some increase in format failure rate is an expected tradeoff of increased randomness, not something eliminable through prompt wording alone. Re-tighten instructions that turned out to have thin margin at low temperature -- explicit, unambiguous formatting instructions degrade more gracefully under higher temperature than implicit ones that only worked because low temperature suppressed deviation.

## Pitfalls
Treating temperature as a single global creativity dial and cranking it up for an entire multi-purpose prompt to get more variety in one part of the output is the core anti-pattern -- it's rarely necessary to sacrifice structural reliability to get creative variation if the two concerns are separated into different calls or guarded independently.

## Verify
At the new temperature setting, run the full pipeline (generation plus any retry/validation logic) against a test set of at least 50 representative inputs and confirm format/structural success rate meets the same bar the low-temperature version met, while independently confirming the creative-quality metric that motivated the change actually improved.
