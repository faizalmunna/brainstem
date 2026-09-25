---
name: prompt-regression-after-model-upgrade
description: A prompt that worked reliably for weeks suddenly produces inconsistent or lower-quality output right after switching model versions or providers.
triggers: ["prompt worked fine until we upgraded the model", "output got worse after switching to the new model version", "regressed after bumping the model id", "same prompt different model different behavior"]
permissions: ["READ"]
---

## Symptom
A prompt that had stable, predictable behavior in development and production suddenly starts producing inconsistent formatting, ignoring instructions it used to follow, or degrading in quality -- and the only change was a model version bump (e.g. pinning to `-latest`, an auto-upgrade, or a deliberate migration to a newer/cheaper model).

## Likely causes
1. **The prompt relied on undocumented model-specific behavior** -- a quirk of how the old model weighted instruction position, handled whitespace, or resolved ambiguity that was never a documented contract, so the new model (even a "better" one) resolves the same ambiguity differently.
2. **Implicit formatting habits changed** -- newer model versions often shift default verbosity, markdown usage, or willingness to add preamble/caveats, which breaks a prompt that never explicitly forbade those behaviors but happened to get lucky before.
3. **The prompt used few-shot examples tuned to the old model's failure modes** -- examples added specifically to correct quirks the old model had, which are now redundant or actively confusing for a model that doesn't share those quirks.
4. **Floating version pin** -- the deployment points at a `-latest` or unpinned alias rather than a specific dated model snapshot, so the underlying model changed silently with no corresponding code or prompt review.
5. **Temperature/sampling defaults or system-prompt handling changed** between versions in ways the application never accounted for, since it assumed the old defaults implicitly.

## Diagnose
- Check whether the deployment pins an exact model snapshot (e.g. a dated version string) or a floating alias, and check provider changelogs/release notes for the exact date of the behavior shift relative to when the regression was noticed.
- Run the exact same prompt and inputs against both the old and new model snapshots side by side (if the old snapshot is still callable) on a fixed test set, and diff the outputs -- not just eyeballing a few, but a batch of at least 20-30 representative production inputs.
- Grep the prompt for instructions that describe *what to avoid* only implicitly (e.g. no explicit "do not add commentary" but relying on the old model's tendency not to) -- these are the most likely fragile spots.
- Check whether any few-shot examples in the prompt were originally added as a patch for a specific old-model failure mode (look at prompt file git history/commit messages for clues like "added example to stop the model from...").

## Fix
Treat the model identifier as a dependency with its own compatibility contract, not an implementation detail: pin to an exact, dated model snapshot in all environments, and treat any move to a new snapshot as a deliberate migration with its own test pass -- never an implicit auto-upgrade. Rewrite instructions that relied on incidental old-model behavior into explicit, model-agnostic constraints (e.g. "respond with only the JSON object, no other text" instead of relying on the model happening not to add commentary). Re-derive few-shot examples from first principles for the target model rather than carrying forward examples that were patches for the old model's specific quirks -- if an example only exists to suppress a failure mode, verify that failure mode still exists on the new model before keeping it.

## Pitfalls
Assuming "newer/bigger model" strictly dominates and skipping re-evaluation entirely is the most common anti-pattern -- a newer model can be more capable in aggregate while still regressing on a specific narrow behavior the old prompt depended on, so aggregate benchmark improvements are not evidence the specific production prompt is fine.

## Verify
Re-run the full regression test set (the 20-30+ representative production inputs from Diagnose) against the new pinned model version and confirm output structure, tone, and instruction-following match the acceptance criteria used for the original prompt, not just spot-checking a handful of "happy path" examples before shipping the pin change.
