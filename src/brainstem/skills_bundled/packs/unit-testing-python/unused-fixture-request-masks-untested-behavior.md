---
name: unused-fixture-request-masks-untested-behavior
description: A test requests a fixture by name in its signature but never actually uses its return value, masking that the test doesn't verify what its name or the fixture's presence implies it does.
triggers: ["fixture requested but not used", "test name implies coverage it lacks", "unused fixture parameter pytest", "test does not test what it claims"]
permissions: ["READ"]
---

## Symptom

Reviewing a test suite, a test's name and its fixture list suggest it
verifies a specific scenario (e.g. `test_handles_expired_token(
expired_token_fixture)`), but the fixture parameter is never referenced
inside the test body -- the test actually exercises something unrelated,
or nothing meaningful at all, despite its name and signature implying
otherwise.

## Likely causes

- **A test was copy-pasted from a similar test that did use the
  fixture**, and during adaptation the fixture parameter was left in the
  signature (for a "just in case" or out of inattention) without actually
  using it in the body.
- **A fixture has an important side effect purely from being
  instantiated** (a `yield`-based fixture that sets up some global state
  or patches something as part of its setup, with no meaningful return
  value the test needs to reference directly) -- in this specific case,
  requesting it without "using" its return value is actually intentional
  and correct, not a bug; this needs to be distinguished from a genuine
  oversight.
- **A refactor removed the code that used to consume the fixture's
  value**, but the fixture parameter itself was never cleaned up
  afterward, leaving a stale signature that no longer reflects what the
  test does.
- **The test's name was written aspirationally** (describing what the
  author intended to test) before the test body was actually finished,
  and was never revisited to confirm the implementation matches the name.

## Diagnose

1. For a test with a suspicious unused-looking fixture parameter, check
   whether the fixture is a "value" fixture (returns something meant to
   be used directly) or a "side-effect" fixture (its setup/teardown is
   the point, regardless of return value) -- linters like `flake8` with
   appropriate plugins, or a manual read, can help distinguish this.
2. If it's a value fixture whose return isn't referenced anywhere in the
   test body, read the test's actual assertions and compare them against
   what the test's name claims to verify.
3. Check git history/blame for the test to see whether the fixture
   parameter was more actively used in an earlier version and was
   orphaned by a later edit.
4. Deliberately break the specific behavior the test's name implies it
   covers (reintroduce a bug related to what the fixture represents) and
   confirm whether the test actually fails.

## Fix

For a genuinely orphaned/unused value fixture, either rewrite the test
body to actually exercise and assert on the fixture's value (closing the
real coverage gap the test's name implies exists), or rename the test to
accurately reflect what it currently verifies and remove the unused
fixture parameter, whichever matches the team's actual intent. Where
possible, add a linter check (many test-linting tools can flag unused
fixture parameters) to catch this pattern automatically going forward,
distinguishing it from legitimate side-effect-only fixture usage via a
naming convention or explicit marker if the tooling supports it.

## Pitfalls

Don't remove a fixture parameter that's actually a legitimate side-
effect-only fixture (no meaningful return value needed) under the
mistaken assumption that "unused" always means "unnecessary" -- verify
which category it is before changing anything, since removing a
side-effect fixture that the test genuinely depends on will silently
break the test's actual (if implicit) coverage.

## Verify

After rewriting the test to genuinely exercise the fixture's value (or
renaming it to match actual behavior), reintroduce the originally
relevant bug and confirm the test now fails as its name/purpose implies
it should.
