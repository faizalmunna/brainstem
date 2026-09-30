---
name: equivalent-mutant-miscounted-as-gap
description: A mutation testing report flags a surviving mutant as a test gap, but the mutation doesn't actually change any observable behavior, wasting investigation time and skewing the mutation score.
triggers: ["equivalent mutant", "mutation testing false positive", "surviving mutant does not change behavior", "mutation score skewed by equivalent mutants"]
permissions: ["READ"]
---

## Symptom

A mutation testing report lists a surviving mutant that, on inspection,
represents a code change that can never actually be observed to differ
from the original code for any real input -- yet it's counted the same
as a genuine test gap, lowering the overall mutation score and
consuming investigation time that would be better spent on real gaps.

## Likely causes

- **A mutation changes dead or unreachable code** (a branch that can
  never actually be taken given the surrounding logic, a default case
  that's provably impossible to hit) so no test could ever kill it
  regardless of test quality.
- **A mutation alters a value in a way that has no observable effect on
  program output** (e.g. changing an internal-only variable that's never
  read, or a redundant computation whose result is discarded).
- **A mutation changes logically equivalent code** (e.g. flipping a
  double-negation, or a boundary condition that happens to coincide with
  another check elsewhere that makes the two versions behaviorally
  identical for all valid inputs).
- **The mutation testing tool doesn't have built-in detection for a
  specific equivalent-mutant pattern** that a different, newer version of
  the tool (or a different tool) might already filter out automatically.

## Diagnose

1. For the specific surviving mutant, read the exact diff between
   original and mutated code and reason carefully about whether any
   possible input could produce a different observable result between
   the two versions.
2. If reasoning alone is inconclusive, write a deliberately targeted test
   attempting to distinguish the two versions -- if no such test can be
   constructed even with real effort, that's strong evidence the mutant
   is equivalent.
3. Check whether the mutation lands in genuinely dead/unreachable code by
   tracing the actual possible control flow paths into that line.
4. Check the mutation testing tool's changelog/documentation for known
   equivalent-mutant detection improvements that a version upgrade might
   already address, before manually triaging one by one.

## Fix

Once genuinely confirmed equivalent (not just assumed), mark the specific
mutant as ignored/excluded using the mutation testing tool's supported
mechanism (most tools support this, keyed to the specific mutation
operator/location), with a comment explaining why it's equivalent so a
future reader doesn't have to re-derive the reasoning. If the mutant
reveals genuinely dead/unreachable code, consider removing that code
entirely as a separate cleanup, since dead code is a maintenance cost
independent of the mutation testing finding.

## Pitfalls

Don't mark a mutant as "equivalent" as a shortcut to improve the score
without genuinely verifying it -- an incorrectly dismissed mutant is a
real test gap wearing a false label, which is worse than an unaddressed
low score because it actively hides the gap from future review. Get a
second opinion or write the distinguishing test attempt before excluding
anything.

## Verify

After excluding a confirmed equivalent mutant, confirm the mutation
testing tool's report no longer flags it on subsequent runs, and confirm
the overall mutation score for the module reflects only genuine,
addressable gaps going forward. Periodically re-review excluded mutants
when the surrounding code changes, since a mutation that was once
equivalent can become a real gap if the code around it changes.
