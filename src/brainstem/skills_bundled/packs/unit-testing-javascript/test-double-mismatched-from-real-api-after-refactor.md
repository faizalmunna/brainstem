---
name: test-double-mismatched-from-real-api-after-refactor
description: Tests keep passing against a hand-written mock even after the real dependency's function signature or response shape changed during a refactor.
triggers: ["mock still passes after api changed", "tests green but function signature changed", "mock out of sync with real implementation", "refactored function but mock never updated", "stale mock after api change"]
permissions: ["READ"]
---

## Symptom
A dependency (an internal service, a class, an exported function) is
refactored -- a parameter is added or renamed, a return shape changes, an
error type changes -- and every test that mocks that dependency continues
to pass unchanged, because the hand-written mock still returns/accepts
whatever it was originally written against. The mismatch is invisible
until the real code paths connect in production or a manual QA pass.

## Likely causes
- **The mock is a hand-written literal object/function with no structural
  connection to the real implementation's type or signature**, so
  TypeScript (if used) can't catch a shape mismatch because the mock was
  never declared `satisfies`/typed against the real interface, and
  JavaScript has no compile-time check at all.
- **The refactor's author updated the real implementation and its direct
  callers, but not the test mocks**, because the mocks live in a
  different file (or many different files) that don't show up in a
  straightforward "find usages" of the changed function the way real call
  sites do, especially when the mock is defined via a string module path
  in `jest.mock('./service')` rather than an explicit reference to the
  real export.
- **The mock was copy-pasted independently into several test files**
  instead of centralized in one shared test-utility/factory, so fixing it
  in the file where the bug was noticed leaves several other copies still
  stale elsewhere in the suite.
- **No contract test or type-level check ties the mock back to the real
  implementation**, so there's no mechanism -- automated or manual -- that
  would ever flag the drift; it only surfaces when a human happens to
  compare the two directly.

## Diagnose
1. For the specific dependency that was refactored, grep for every
   `jest.mock(`/`vi.mock(`/manual mock object referencing it
   (`__mocks__/<name>.js`, inline factory mocks, hand-built stub objects)
   across the whole test tree, not just the file where the bug was
   noticed -- this finds every stale copy, not just one.
2. Compare each mock's return shape and accepted arguments directly
   against the real, current implementation's type definition or actual
   runtime behavior -- if using TypeScript, check whether the mock object
   is annotated with the real interface/type at all (`satisfies
   RealServiceType`) or is just an untyped object literal.
3. Check whether a contract test, a Pact test, or even a simple
   generated-type-based mock factory exists anywhere in the codebase for
   this dependency -- if the only thing connecting the mock to reality is
   a human's memory, that's the structural gap.
4. Run the real dependency directly (in a script, REPL, or an integration
   test against a test instance) with the same inputs the mock is
   configured to receive, and diff its actual current output against
   what the mock returns.

## Fix
Type the mock against the real implementation's actual interface wherever
TypeScript is available (`const mockService: jest.Mocked<RealService> =
{...}` or a `satisfies` assertion), so a shape drift becomes a compile
error the next time the real interface changes, rather than a silent
runtime mismatch. Centralize commonly-mocked dependencies into a single
shared factory function (`createMockUserService(overrides?)`) that every
test file imports, instead of each file hand-rolling its own mock
literal, so a fix to the shared factory propagates everywhere at once
instead of needing to be found and fixed in each copy. For dependencies
important enough to warrant it, add a contract test (via Pact or a
lightweight schema check) that validates the mock's shape against the
real implementation's actual behavior on a schedule or in CI, catching
drift automatically instead of relying on someone noticing during a code
review.

## Pitfalls
Don't respond to a discovered mock/reality mismatch by deleting the mock
and calling the real dependency directly in every test "to be safe" --
that reintroduces the slowness/flakiness/external-dependency problems
mocking existed to solve; fix the mock's fidelity (typing, centralization,
contract validation) instead of removing mocking as a technique. Also
don't centralize a mock factory and then immediately override most of its
fields inline in every call site anyway -- if every test needs
substantially different behavior from the shared factory, the factory
isn't actually capturing the real shape usefully and needs
reconsideration, not just wider adoption.

## Verify
After typing or centralizing the mock, deliberately change the real
implementation's signature or return shape in a scratch branch (rename a
field, add a required parameter) without touching any test file, and
confirm the change now produces a compile error (typed mock) or a failing
contract test, rather than every test continuing to pass silently against
the now-stale mock.
