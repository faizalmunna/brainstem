---
name: nondeterministic-test-from-unmocked-date-or-random
description: A test fails intermittently or produces a different result on each run because it depends on the real system clock or an unmocked random number generator.
triggers: ["flaky test date now", "test fails randomly math random", "test passes locally fails in ci intermittently", "date dependent test flaky", "uuid changes every run breaks snapshot"]
permissions: ["READ"]
---

## Symptom
A test passes most of the time but occasionally fails with a value that's
"close but not equal" to expected (an age calculation off by one, a
timestamp comparison failing near midnight or a DST boundary), or a
snapshot/assertion involving a generated ID, timestamp, or random value
differs on every single run -- yet the underlying logic under test hasn't
changed at all.

## Likely causes
- **The code under test calls `Date.now()`/`new Date()` directly** and the
  test asserts against a value computed independently at test-write time
  (a hardcoded expected timestamp, or a relative comparison like "should
  be today"), so the assertion only holds within a narrow time window or
  breaks entirely across a day/month/year/DST boundary.
- **`Math.random()` (or a UUID generator built on it) is called
  un-mocked** inside code whose output the test asserts on exactly (a
  generated ID embedded in a snapshot, a random-order shuffle whose exact
  result is checked), so the test can only ever pass by coincidence or
  never pass consistently at all.
- **Fake timers were set up for `setTimeout`/`setInterval` behavior but
  `Date` itself wasn't included in what's faked**, so timer-driven code
  paths are deterministic while any `Date.now()` call elsewhere in the
  same code path still reads the real, advancing system clock mid-test.
- **A dependency several layers down (a logging library timestamp, an ORM
  default `createdAt`, a JWT `iat`/`exp` claim) generates a real
  timestamp or random value that surfaces into the test's assertion
  indirectly**, so the flakiness doesn't come from code the test author
  wrote directly, making it harder to spot by reading the test alone.

## Diagnose
1. Run the specific test many times in a tight loop
   (`for i in {1..50}; do npx jest path/to/test -t "test name"; done` or
   the project's repeat-run flag) and check whether failures cluster
   around specific moments (e.g. only fails near a minute/hour boundary)
   -- that timing pattern points directly at an unmocked clock.
2. Grep the code under test (not just the test file) for `Date.now()`,
   `new Date()`, and `Math.random()` calls, including inside any
   dependency the function calls directly -- indirect timestamp/random
   sources (ORM defaults, ID generators, JWT libraries) are easy to miss
   by reading only the test.
3. Diff two consecutive real run outputs of the failing assertion (log the
   actual received value on each run) to see whether the difference is
   consistent with a clock tick or a random value, versus a genuinely
   different logic result -- this distinguishes "needs mocking" from "an
   actual bug."
4. Check whether fake timers are already in use in the file
   (`useFakeTimers()`) and, if so, whether `Date` is included in the faked
   API set for this Jest/Vitest version's default configuration, since
   defaults have changed across versions.

## Fix
Mock the specific nondeterministic source at its actual call site rather
than working around its symptom in the assertion: use
`jest.useFakeTimers().setSystemTime(fixedDate)` /
`vi.setSystemTime(fixedDate)` to pin `Date.now()`/`new Date()` to a fixed,
known instant for the duration of the test, and `jest.spyOn(Math, 'random')
.mockReturnValue(fixedValue)` / the Vitest equivalent to make
random-dependent output deterministic. For indirect sources (a UUID
library, an ORM's default timestamp), inject or mock that specific
dependency (pass a clock/id-generator as a parameter, or mock the library
module directly) rather than mocking `Date`/`Math.random()` globally and
hoping it propagates correctly through every layer. Where the assertion
genuinely needs to compare "close to now" rather than an exact value,
assert against a tolerance range or a mocked-but-realistic delta instead
of an exact equality check on a live clock read.

## Pitfalls
Don't "fix" the flake by widening the assertion's tolerance (e.g.
allowing a multi-second delta) instead of pinning the clock -- this
converts an occasionally-flaky test into a rarely-flaky one that fails
the same way eventually, and it also weakens the test's ability to catch
a genuine off-by-a-large-amount bug in time-based logic. Also don't mock
`Date` globally in a shared setup file without restoring it after each
test -- a leaked fixed `Date.now()` from one test can make an unrelated
later test that expects real time silently wrong in the other direction.

## Verify
Run the fixed test in the same tight repeat loop used during diagnosis
(fifty-plus consecutive runs) and confirm identical pass results and
identical asserted values every time, including runs executed right at a
day/hour boundary if that's achievable by setting the mocked system time
explicitly to that boundary as part of the test.
