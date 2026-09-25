---
name: accidentally-skipped-test-reports-as-passing
description: A test that should be running and catching a known bug shows up as passing in CI because it was silently skipped rather than actually executed.
triggers: ["test suite green but test never ran", "test.skip left in code", "describe.only excluding other tests", "jest test not actually running", "ci passing but test was skipped"]
permissions: ["READ"]
---

## Symptom
CI reports the full suite as green, but a specific test that should be
exercising a known bug or a recent feature never actually ran -- it was
skipped, filtered out, or excluded, and the test runner's summary line
(easy to miss among hundreds of tests) says something like "1 skipped"
rather than failing the build. The team believes a behavior is covered
because a test with the right name exists in the repo.

## Likely causes
- **`.skip`/`xdescribe`/`xit` was added temporarily while debugging or
  during a flaky-test triage, and the removal was forgotten** before
  merging -- a common pattern is skipping a test to unblock a PR with an
  intention to fix it "in a follow-up" that never happens.
- **`.only` was left on a different `describe`/`it` block in the same
  file (or, depending on runner config, the same run)**, which causes
  every other test to be implicitly skipped for that run without any of
  them being individually marked -- easy to miss because the skipped
  tests don't have any visible marker on themselves at all.
- **A typo in the test name/tag used with a `--testNamePattern`/`-t`
  filter in CI config** causes the intended test (or an entire file) to
  never match the filter and silently not run, while the CI step itself
  still exits successfully since zero matched tests isn't treated as a
  failure by default.
- **A conditional skip based on environment** (`if (process.env.CI) return;`
  or `test.skip(isCI, 'flaky in CI')`) was added to work around an
  environment-specific issue and never revisited, meaning the test
  effectively never runs in the one environment (CI) where catching
  regressions matters most.

## Diagnose
1. Read the actual test run summary line, not just the exit code --
   Jest/Vitest print explicit "X skipped" counts distinct from "X passed";
   a nonzero skipped count on a suite believed to be fully active is the
   direct signal.
2. Grep the test tree for `.skip(`, `.only(`, `xdescribe`, `xit`,
   `xtest`, and any environment-conditional early `return`/`skip` inside
   a test body -- these are all textually greppable even though they
   don't fail the build.
3. Check CI configuration for `--testNamePattern`/`-t`/`--grep` filters
   and manually verify the pattern actually matches the intended test
   name by running the same filter locally and checking the reported
   test count against the expected total.
4. Compare the total test count over time (a CI dashboard, or just
   `grep -rc "it(\|test(" ` across the suite) against the number actually
   executed in the latest run -- a growing gap between "tests written" and
   "tests executed" indicates accumulating silent skips.

## Fix
Configure the test runner (or a CI lint step) to fail the build on any
`.only` found in the committed test tree -- most runners/ESLint plugins
(`eslint-plugin-jest`'s `no-focused-tests`, `no-disabled-tests`) can flag
or error on `.only`/`.skip` usage specifically, turning an easy-to-miss
silent skip into a loud lint failure before merge. For legitimately
temporary skips, require a linked tracking issue/ticket in the skip
reason (`it.skip('...', () => {})` with a comment referencing a ticket) and
periodically audit `.skip` usage as its own backlog item rather than
letting it accumulate indefinitely. For `-t`/`--testNamePattern` based CI
filtering, assert on the actual executed test count in the CI script
itself (fail if fewer than an expected minimum ran) so a filter typo that
silently matches zero tests breaks the build instead of passing quietly.

## Pitfalls
Don't remove a `.skip` and immediately "fix" the test by loosening its
assertions just to make it pass without investigating why it was skipped
in the first place -- a test skipped because it was catching a real,
still-unfixed bug needs the bug fixed, not the test weakened until it
agrees with the buggy behavior. Also don't rely on manually remembering to
search for `.only` before every commit -- it's exactly the kind of thing
a lint rule catches reliably and human review doesn't, especially in a
large diff.

## Verify
Add the lint rule (or CI count-based check) for `.only`/silent-skip
patterns, then deliberately add a `.only` to a test locally and confirm
the lint step or CI check fails the build -- this proves the guardrail
actually catches the exact failure mode being guarded against, not just
that it's configured.
