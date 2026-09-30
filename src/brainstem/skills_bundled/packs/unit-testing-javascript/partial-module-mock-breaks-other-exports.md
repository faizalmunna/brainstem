---
name: partial-module-mock-breaks-other-exports
description: Mocking one function from a module makes every other export from that same module become undefined inside the code under test.
triggers: ["jest.mock breaks other exports undefined", "vi.mock only mocking one function breaks module", "requireActual needed", "importOriginal vitest partial mock", "mocked module other functions undefined"]
permissions: ["READ"]
---

## Symptom
A test calls `jest.mock('./utils')` (or `vi.mock('./utils', ...)`)
intending to stub out just one function from that module, but the code
under test then throws `TypeError: someOtherExport is not a function` (or
silently gets `undefined`) for every *other* export from that same
module -- functions the test never intended to touch and that have
nothing to do with what's being tested.

## Likely causes
- **`jest.mock('./utils')` with no factory function auto-mocks every
  export in the module**, replacing each one with a `jest.fn()` that
  returns `undefined` by default -- calling any un-configured export from
  that module then returns `undefined` instead of running its real
  implementation, breaking any code path that depends on a different
  function from the same file.
- **A factory function is provided but only defines the one export the
  test cares about**, e.g. `jest.mock('./utils', () => ({ formatDate:
  jest.fn() }))`, which replaces the *entire* module's export object with
  exactly that literal -- every other real export simply no longer exists
  on the mocked module object at all.
- **The module groups genuinely unrelated utilities together** (a single
  `utils.js` exporting date formatting, string helpers, and validation
  logic), so mocking "the module" to control one narrow piece of behavior
  has a much larger blast radius than the test author intended, because
  the module's boundary doesn't match the test's actual intent.
- **`jest.requireActual`/`vi.importActual` (or Vitest's `importOriginal`
  in `vi.mock`'s factory) is not used to preserve the real
  implementations of the exports that shouldn't be mocked**, so there's no
  mechanism keeping the untouched exports real.

## Diagnose
1. Read the exact error/stack trace -- if it names a function from the
   same module path as the one being mocked, but a function the test
   never referenced directly, that's the signature of this exact pattern
   rather than a bug in test logic.
2. Check the `jest.mock`/`vi.mock` call for the module in question:
   no factory (full auto-mock) versus a factory object literal that only
   lists some exports -- either form replaces the whole module's export
   surface, just via different mechanisms.
3. Open the real module file and list every export versus what the mock
   factory defines -- the difference is exactly the set of functions that
   will now be `undefined`/missing wherever this mock is active.
4. Check whether other tests for the *same* code path (that don't mock
   this module at all) pass -- if they do, this confirms the break is
   specific to the mocking setup, not the code under test's own logic.

## Fix
When only one or two exports from a module need mocking, preserve the
rest with `jest.requireActual`/`vi.importActual` (or `importOriginal`
inside Vitest's `vi.mock` factory) spread into the factory's returned
object: `jest.mock('./utils', () => ({ ...jest.requireActual('./utils'),
formatDate: jest.fn() }))`, so every export other than the explicitly
mocked one keeps its real implementation. Where a module bundles clearly
unrelated concerns (date formatting alongside validation alongside string
helpers), consider splitting it into separate, single-purpose modules --
this shrinks the blast radius of mocking any one of them and often
reflects better module boundaries independent of testing concerns.
Alternatively, mock only the specific function via dependency injection
(pass it as a parameter/prop to the code under test) instead of mocking
the whole module, when the code under test's design allows it.

## Pitfalls
Don't reach for `jest.requireActual` as a reflexive default on every
`jest.mock` call "just in case" -- spreading the real module into every
mock factory can accidentally keep real, slow, or side-effecting code
running when the intent actually was to mock the entire module (e.g. a
module that opens a real database connection at import time). Use it
deliberately, only when specific other exports are known to be needed
unmocked. Also don't solve this by manually re-implementing every other
export inside the mock factory one by one -- that duplicates the real
implementation in test code and silently drifts out of sync with it over
time (see the companion skill on mocks going stale after a real
refactor).

## Verify
Run the test with the fixed mock and add a temporary assertion that calls
one of the previously-broken, unrelated exports directly, confirming it
returns its real, correct value rather than `undefined` -- then remove the
temporary assertion once confirmed, leaving the `requireActual` spread (or
module split) as the permanent fix.
