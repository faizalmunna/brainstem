---
name: over-mocked-class-hides-untested-method-bug
description: An entire class is mocked when only one method needed to be, silently leaving every other method on that class completely untested and free to contain real bugs.
triggers: ["mocked whole class instead of method", "unittest mock hides real bug", "over-mocking python test", "class mock too broad"]
permissions: ["READ"]
---

## Symptom

A real bug in a method of a class ships to production despite tests
existing that use that class, because the tests mock the entire class
(`mock.patch('module.MyClass')` or `MagicMock(spec=MyClass)` used broadly)
rather than mocking only the one specific method that needed to be
isolated -- every other method's actual behavior was never exercised.

## Likely causes

- **A test needed to isolate one expensive or side-effecting method**
  (a network call, a database write) but mocked the entire containing
  class as the easiest way to prevent that one call, incidentally
  replacing every other method with a generic mock too.
- **A shared test setup/fixture mocks a class broadly "just in case"**
  for convenience across many tests, without each individual test
  narrowing the mock to only what it actually needs to isolate.
- **`MagicMock()` without `spec=` or `autospec=True` was used**, so the
  mock object accepts calls to *any* method name (even ones that don't
  exist on the real class) without complaint, making it easy to not
  notice that most of the class's real behavior is bypassed.
- **The class under test has a large public interface**, and mocking it
  wholesale felt simpler than identifying and mocking the one
  problematic dependency it has internally.

## Diagnose

1. For the class involved in the shipped bug, check the relevant test's
   mock setup -- is the entire class replaced with a mock, or only a
   specific method/dependency?
2. Check whether the mock uses `spec=` or `autospec=True` -- an unspecced
   `MagicMock` accepting arbitrary method calls without validation is a
   strong signal of overly broad, low-fidelity mocking.
3. Identify what the test was actually trying to isolate (usually a
   single expensive/side-effecting dependency) versus what it ended up
   mocking (the whole class), to scope a narrower fix.
4. Check whether other tests exist that exercise the specific method that
   had the bug in an unmocked way -- if none do, this confirms the
   coverage gap concretely.

## Fix

Mock only the specific method or dependency that actually needs
isolating (the expensive/side-effecting one), letting the rest of the
class's real methods execute normally during the test, so their actual
behavior is genuinely exercised and verified. Use `autospec=True` (or
`spec=RealClass`) whenever mocking is necessary, so the mock's interface
is validated against the real class and typos/removed methods are caught
rather than silently accepted. Where a dependency genuinely needs full
isolation (an external service client), inject it as a separate,
narrowly-scoped collaborator rather than mocking the class that uses it,
so the class's own logic remains testable independently of that one
dependency.

## Pitfalls

Don't swing to the opposite extreme and eliminate all mocking, turning
every unit test into a slow, brittle integration test against real
external dependencies -- the goal is scoping mocks precisely to what
genuinely needs isolating (external calls, non-deterministic behavior),
not avoiding mocking altogether. Balance isolation of the specific
expensive/side-effecting call against exercising as much real logic as
practical.

## Verify

After narrowing the mock's scope, deliberately reintroduce the original
shipped bug in the previously-unmocked method and confirm the test suite
now catches it. Confirm the narrowed mock still successfully isolates the
originally problematic dependency (no real network call/database write
occurs during the test run).
