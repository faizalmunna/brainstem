---
name: test-order-dependency-random-order-reveals
description: Tests pass reliably when run in their default order but fail when run in a randomized order, revealing a hidden dependency on shared or leftover state between tests.
triggers: ["tests fail with pytest-randomly", "test order dependency", "tests pass in default order fail randomized", "hidden shared state between tests"]
permissions: ["READ"]
---

## Symptom

A test suite passes reliably in its normal run order, but enabling test
randomization (via `pytest-randomly` or a similar plugin) causes specific
tests to fail intermittently depending on what order they happen to run
in relative to certain other tests.

## Likely causes

- **A module-level or class-level mutable variable is modified by one
  test and read by another**, with the default alphabetical/file-based
  run order happening to always execute the "setup" test before the
  "dependent" test, an ordering randomization doesn't preserve.
- **A fixture with broader-than-`function` scope (`module`, `session`)
  holds mutable state that one test mutates**, assuming (incorrectly)
  that later tests using the same fixture instance will see a fresh
  value, when in fact they see whatever the previous test left behind.
- **Tests rely on a specific database/filesystem state left over from an
  earlier test** (a specific row existing, a specific file being present)
  without either creating that state themselves or the test framework
  guaranteeing that ordering.
- **A test modifies global process state** (an environment variable, a
  monkeypatched global, a class attribute) without properly resetting it
  in teardown, and a later test's behavior depends on that global's
  original, unmodified value.

## Diagnose

1. Run the suite with randomization enabled repeatedly and note which
   specific test(s) fail and with which specific other tests they appear
   in the run alongside beforehand -- the plugin usually reports the
   random seed used, which allows exact reproduction of a specific
   failing order.
2. Use the reported seed to reproduce the exact failing order locally,
   then bisect by running smaller subsets of the suite in that same
   relative order to narrow down which specific pair (or small group) of
   tests interacts badly.
3. Once the interacting tests are identified, inspect what shared state
   (module-level variables, broader-scoped fixtures, global environment)
   both tests touch.
4. Check fixture scope declarations (`@pytest.fixture(scope=...)`) for
   anything broader than `function` that holds mutable state modified by
   tests using it.

## Fix

Scope fixtures to `function` (the pytest default) unless a broader scope
is specifically needed for performance reasons, and if a broader-scoped
fixture is kept for performance, make sure any mutable state it provides
is either reset between tests or made immutable/read-only from the
tests' perspective. Eliminate module-level or class-level mutable
variables used as ad hoc shared state between tests, replacing them with
fixtures that provide fresh state per test. For any test that
monkeypatches or modifies global/environment state, use `monkeypatch`
(which pytest automatically reverts after each test) rather than manual
mutation without guaranteed cleanup.

## Pitfalls

Don't respond to a discovered order-dependency by pinning the test suite
to always run in the specific order that happens to pass -- that papers
over the underlying shared-state bug (which can still bite in CI
environments or future test additions that change effective ordering)
rather than fixing the actual test isolation problem. Fix the isolation,
don't just avoid triggering the symptom.

## Verify

Re-run the full suite with randomization enabled repeatedly (multiple
different seeds) and confirm no further order-dependent failures appear.
Specifically re-run using the original failing seed and confirm it now
passes, as direct confirmation the specific interaction was fixed.
