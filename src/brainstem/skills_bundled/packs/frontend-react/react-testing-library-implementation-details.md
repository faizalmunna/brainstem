---
name: react-testing-library-implementation-details
description: Fix brittle React Testing Library tests that break on harmless refactors because they assert on implementation details instead of user-observable behavior.
triggers: ["testing library test breaks on refactor", "brittle react test", "test fails after renaming", "shallow rendering vs testing library", "test implementation details"]
permissions: ["READ"]
---

## Symptom
A component test fails after a purely internal refactor (renaming a
prop, changing internal state shape, restructuring child components)
that didn't change any user-visible behavior -- the test was coupled to
*how* the component works, not *what* it does.

## Likely causes
1. **Querying by CSS class name, component display name, or DOM
   structure** (`container.querySelector('.card-title')`,
   `wrapper.find('SomeInternalComponent')`) instead of by accessible role/
   text/label -- these break the moment a class or internal component
   name changes, even if the rendered UI looks identical to a user.
2. **Asserting on internal state or props directly** via a test-only
   escape hatch instead of asserting on rendered output -- couples the
   test to implementation, not behavior.
3. **Snapshot tests of large component trees** that fail on any markup
   change, trivial or not, training the team to blindly accept snapshot
   diffs rather than review them -- a specific failure mode of snapshot
   testing, not testing in general.
4. **Testing a child component's internals through the parent** instead
   of testing the parent's behavior at its own boundary and the child
   separately.

## Diagnose
- For a newly-broken test after a refactor, check what the test actually
  queries/asserts on: is it something a real user would see/do (visible
  text, an accessible role, an input's value), or something only visible
  in the implementation (a class name, an internal prop, a snapshot of
  full markup)?
- Check whether the test would still pass if the component were rewritten
  entirely differently internally but produced the same rendered result
  and behavior -- if not, it's coupled to implementation.

## Fix
- Query by role, label, or visible text (`getByRole('button', { name:
  /submit/i })`, `getByLabelText('Email')`) rather than by class name or
  test-only selectors, unless there's genuinely no accessible way to
  identify the element (in which case, that's also an accessibility gap
  worth fixing in the component itself).
- Assert on what the user would observe: text appearing/disappearing, a
  button becoming enabled/disabled, an input's displayed value -- not on
  internal state or the exact DOM structure.
- Replace large full-tree snapshot tests with targeted assertions on the
  specific behavior under test, or scope snapshots to small, stable
  pieces of output where a diff is actually meaningful to review.
- Test child components' own behavior in their own test file; test the
  parent's behavior (what it renders/does based on its own props/state),
  treating children as already-tested units, not re-verifying their
  internals through the parent.

## Pitfalls
- Switching everything to `data-testid` attributes avoids some brittleness
  but throws away the accessibility-testing benefit of querying by role/
  label (a test that only passes via `data-testid` can pass even if the
  component is inaccessible to real assistive technology) -- prefer
  role/label queries first, `data-testid` as the fallback when there's
  truly no accessible identifier.
- Removing all snapshots in reaction to brittleness can lose real
  regression coverage for visual/structural output that *should* be
  caught -- the fix is scoping and reviewing snapshots meaningfully, not
  eliminating the tool.

## Verify
Make a purely internal refactor (rename an internal variable, restructure
child components without changing rendered output or behavior) and
confirm the test suite still passes -- if it doesn't, the test was
coupled to implementation, not behavior, and needs the fix above.
