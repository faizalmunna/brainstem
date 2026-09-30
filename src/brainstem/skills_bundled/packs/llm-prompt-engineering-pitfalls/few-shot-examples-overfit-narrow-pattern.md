---
name: few-shot-examples-overfit-narrow-pattern
description: Few-shot examples in a prompt bias the model toward one narrow input shape, causing it to fail on legitimate inputs that don't match that shape.
triggers: ["model only works for inputs like the examples", "few shot examples are biasing the output", "model ignores inputs that look different from the examples", "works for short inputs fails for long ones after adding examples"]
permissions: ["READ"]
---

## Symptom
After adding a few worked examples to a prompt to improve consistency, the model starts performing worse on a subset of real inputs -- it forces outputs into the exact structure/length/category distribution of the examples even when the actual input clearly calls for something different, or it fails outright on inputs that don't superficially resemble any example.

## Likely causes
1. **Examples share an incidental surface pattern** the model latches onto (e.g. all examples happen to be short, all in English, all have exactly 3 output items) that was never actually a rule, so the model treats accidental shared traits as if they were the specification.
2. **Examples don't cover the actual input distribution** -- they were picked because they were convenient or the first ones the author thought of, not sampled from real production traffic, so entire legitimate input categories have no representative example.
3. **Too few examples relative to the diversity of the task**, so the model over-generalizes from a small, biased sample rather than learning the actual underlying rule the examples were meant to illustrate.
4. **Examples demonstrate the common case but not edge cases**, and the model has no signal about how to handle inputs that fall outside what was shown, so it either forces the common-case template onto them or fails unpredictably.
5. **Example order or recency effects** -- one example (often the last one, due to recency bias in the context) dominates the model's behavior disproportionately relative to the others.

## Diagnose
- Segment production failure cases by how similar they are to the few-shot examples (length, language, category, structure) and check whether failures cluster specifically among inputs that differ from the examples along some dimension -- that dimension is the overfit axis.
- Temporarily remove the few-shot examples entirely and compare zero-shot behavior against the failing inputs -- if the model handles the edge cases better without examples (at the cost of some consistency elsewhere), the examples are actively teaching the wrong constraint.
- Audit the example set for accidental shared traits: length, format, language, tone, domain -- anything consistent across all examples that isn't actually part of the task specification is a candidate for what the model over-learned.
- Check how the examples were originally selected -- if they were hand-picked or the first few that came to mind rather than sampled from real traffic, that's the root cause, not a symptom to patch around.

## Fix
Rebuild the few-shot set by sampling deliberately from the actual production input distribution, including edge cases and minority categories, not just the common case -- the goal is examples that jointly demonstrate the range of valid variation, not just one clean template repeated with different words. Where the underlying rule can be stated directly in instructions, do so explicitly rather than relying on the model to infer it correctly from examples alone -- examples should illustrate the instructions, not substitute for them. If an edge case is important and rare, include at least one example specifically for it rather than assuming the model will generalize to it from common-case examples.

## Pitfalls
Simply adding more examples of the failing edge case without reconsidering the whole set often trades one narrow bias for another -- if the new examples now dominate the prompt, the model may overcorrect and start forcing the edge-case pattern onto common inputs; example set changes need to be evaluated against the full input distribution, not just the case that just failed.

## Verify
Run the updated example set against a stratified evaluation set that deliberately includes both the common case and every known minority/edge case category at a realistic proportion, and confirm accuracy holds across all strata -- not just an aggregate score that a majority-case improvement could mask a minority-case regression behind.
