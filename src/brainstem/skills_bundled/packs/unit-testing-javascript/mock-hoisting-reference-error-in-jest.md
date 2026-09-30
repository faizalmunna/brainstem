---
name: mock-hoisting-reference-error-in-jest
description: A jest.mock or vi.mock factory throws a ReferenceError about accessing a variable before initialization even though the variable is clearly declared above it in the file.
triggers: ["jest.mock cannot access before initialization", "vi.mock referenceerror", "jest mock factory out of scope variable", "the module factory of jest.mock is not allowed to reference", "vi.hoisted needed"]
permissions: ["READ"]
---

## Symptom
A test file that looks syntactically correct -- a variable declared near
the top, then referenced inside a `jest.mock('./module', () => ({ ... }))`
factory a few lines below it -- throws `ReferenceError: Cannot access
'someVar' before initialization`, or Jest raises its own explicit error
that the module factory isn't allowed to reference out-of-scope variables
(names starting with `mock` are sometimes allowed, everything else isn't).

## Likely causes
- **`jest.mock()` calls are hoisted by Jest's babel/TS transform to the
  top of the file**, above all `import` statements and `const`/`let`
  declarations, specifically so mocks are in place before the module
  under test imports its dependencies -- any variable the factory
  function references that was declared with normal `const`/`let` in the
  file body is therefore not yet initialized at the point the hoisted
  factory actually runs.
- **Vitest does not auto-hoist `vi.mock()` the same way in all cases**
  (its hoisting is more limited/explicit than Jest's), so code copied from
  a Jest codebase that relied on implicit hoisting behavior can fail
  differently or silently not mock what the author expects under Vitest,
  requiring `vi.hoisted()` to explicitly lift a variable's initialization
  above the mock factory.
- **The factory references an imported module-level constant** (an
  imported fixture object, a constant imported from another test-helper
  file) rather than a value declared inline in the same file, so even
  understanding "hoisting moves my `const` down" doesn't explain the
  failure -- the real issue is that the import itself hasn't run yet
  either, for the same hoisting reason.
- **A team convention of naming mock-related variables without the
  `mock`-prefix Jest specifically allows** (Jest permits referencing
  variables whose name starts with `mock` inside the factory, as a
  documented escape hatch) means an otherwise-fine variable trips the
  restriction purely because of its name, not its actual usage.

## Diagnose
1. Read the exact error message closely -- Jest's own explicit hoisting
   error names the specific out-of-scope variable and states the
   `mock`-prefix rule directly; a generic `ReferenceError: Cannot access
   'x' before initialization` (without Jest's custom message) usually
   means the same hoisting mechanics but via a plain JS temporal-dead-zone
   error instead of Jest's guard.
2. Confirm which test runner is in use and check its specific hoisting
   docs/behavior for `jest.mock()`/`vi.mock()` -- Jest hoists
   automatically via `babel-plugin-jest-hoist`; Vitest requires
   `vi.hoisted()` for values a mock factory needs that aren't simple
   inline literals.
3. Check whether the referenced variable's name starts with `mock` --
   if renaming it to `mockSomething` alone resolves a Jest-specific error
   (not a Vitest one), that confirms it was Jest's naming-convention
   restriction specifically, not a deeper scoping problem.
4. Trace whether the value referenced in the factory comes from an
   `import` versus a same-file `const` -- imports are also subject to the
   same hoisting-order issue, since the mock factory can run before any
   of the file's own import statements have executed.

## Fix
For Jest, either name the variable with a leading `mock` (satisfying
Jest's explicit allowlist for out-of-scope references, e.g. `mockGetUser`
instead of `getUserStub`), or avoid referencing an outer variable
entirely by constructing the mock's return value fully inline inside the
factory function. For Vitest, wrap the value in `vi.hoisted(() => ({...}))`
so its initializer is explicitly lifted to run before the hoisted
`vi.mock()` call, then reference the `vi.hoisted()` result inside the
factory -- this makes hoisting explicit rather than relying on implicit
transform behavior that differs from Jest's. When the mock needs a value
that's genuinely computed elsewhere (a shared fixture), import it inside
the factory function's own body (a dynamic `require`/inline import) rather
than closing over an outer-scope binding, since requiring the module
fresh inside the factory sidesteps the temporal-dead-zone issue entirely.

## Pitfalls
Don't "fix" this by converting the mock factory to reference a
`var`-declared variable instead of `const`/`let` -- `var`'s hoisting
avoids the ReferenceError by making the variable `undefined` instead of
throwing, which silently produces a broken mock (returning `undefined`
where a real value was expected) rather than a clear error, trading a
loud failure for a confusing silent one. Also don't blanket-rename
every mock-adjacent variable to start with `mock` as a habit without
understanding why -- it works around Jest's specific allowlist but does
nothing for Vitest, and doesn't fix the underlying case where the
referenced value is an import rather than a local constant.

## Verify
Run the specific test file and confirm it executes without any
`ReferenceError`/hoisting error, then log the mock factory's return value
at the top of a test using it to confirm it's the intended real value
(not `undefined` from a `var`-hoisting workaround) before asserting
anything else in the test.
