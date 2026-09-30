---
name: no-seam-found-tightly-coupled-legacy-code
description: A team can't find a safe place to insert a test or introduce an abstraction boundary in tightly-coupled legacy code, so every attempted refactor ends up touching far more than intended.
triggers: ["cannot find a seam in legacy code", "tightly coupled code hard to refactor", "every change touches too much", "no place to insert a test boundary"]
permissions: ["READ"]
---

## Symptom

An attempt to refactor or add tests to a legacy module keeps expanding
in scope -- every place the team tries to introduce a clean boundary
(to mock a dependency, to isolate a piece of logic for testing) turns
out to be entangled with several other things, so the "small, safe"
change keeps growing into a much larger one, and the refactor gets
abandoned as too risky.

## Likely causes

- **The module was written with no separation between business logic and
  its dependencies** (direct calls to a database, a file system, a
  global singleton) scattered throughout, so there's no natural
  boundary where a test double or abstraction could be inserted without
  touching the surrounding code.
- **Global/shared mutable state is read and written from many different
  places in the module** (or across modules), so isolating any one piece
  of behavior for testing requires understanding and controlling that
  shared state, which itself is touched by code far outside the area
  being refactored.
- **Function/method boundaries don't align with logical units of
  behavior** -- a single large function does several unrelated things,
  so there's no way to test or isolate one piece of its logic without
  either testing the whole function (with all its dependencies) or
  first splitting it apart, which is itself a refactor requiring
  confidence the team doesn't yet have.
- **The team is looking for a "big" seam (a major architectural boundary)
  when a much smaller one would actually suffice** to start -- expecting
  the first refactoring step to be transformative rather than minimal.

## Diagnose

1. Read through the specific module looking not for an ideal
   architectural boundary, but for the single smallest possible change
   that would let one specific behavior be tested in isolation --
   Michael Feathers' "seams" concept specifically as a search for the
   smallest workable insertion point, not a redesign.
2. Identify which dependencies (database calls, file I/O, global state)
   a specific piece of logic actually touches, to scope exactly what
   would need to be substitutable to test that logic alone.
3. Check whether the language/runtime offers any low-risk seam-creation
   technique specific to it (e.g. extracting a method and calling it
   through an overridable reference, wrapping a global with an
   injectable accessor) that doesn't require a large structural change.
4. Identify the actual smallest subset of behavior worth testing first,
   rather than trying to find a seam for the whole module at once.

## Fix

Introduce the smallest possible seam -- often just extracting one
tightly-scoped piece of logic into its own function/method with explicit
parameters instead of reaching into global state or calling a dependency
directly, then passing that dependency in rather than reaching out for
it internally. This is often called "preparatory refactoring": a small,
behavior-preserving change whose only purpose is to make a later change
possible, done as its own step with its own care, before the actual
refactor/test-writing begins. Start with the smallest, most isolated
piece of behavior rather than trying to seam the whole module in one
attempt, building confidence and technique on smaller wins first.

## Pitfalls

Don't attempt a large structural refactor to "properly" decouple
everything in one pass, driven by frustration at not finding an easy
seam -- that's exactly the large, risky change the team was trying to
avoid by looking for a seam in the first place. The point of seam-finding
is minimality; resist the urge to over-engineer the first insertion
point.

## Verify

After introducing the minimal seam, confirm the specific piece of logic
can now be tested in isolation (with its dependency substituted for a
test double), and confirm the module's existing behavior is otherwise
completely unchanged (via manual verification or existing
characterization tests) -- the seam-introduction step itself should be
behavior-preserving, verifiably.
