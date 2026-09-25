---
name: cypress-custom-command-loses-chainability
description: A custom Cypress command breaks the command chain, causing subsequent .then() calls or assertions to receive the wrong subject or fail type checking after a refactor.
triggers: ["cypress custom command not chainable", "cypress command returns wrong subject", "custom command breaks then chain", "cypress command typescript type error after refactor"]
permissions: ["READ"]
---

## Symptom

After adding or refactoring a custom Cypress command
(`Cypress.Commands.add(...)`), code that chains further commands or
`.then()` callbacks off of it either fails at runtime with the wrong
subject being passed through, or (in a TypeScript setup) produces type
errors that didn't exist before the custom command was introduced.

## Likely causes

- **The custom command doesn't explicitly return the correct Cypress
  chainable subject**, so whatever it happens to return (or fails to
  return) becomes what's passed to the next command in the chain, rather
  than the intended element/value.
- **A custom command was registered with `{ prevSubject: true }` (or a
  specific prevSubject type) inconsistently with how it's actually
  invoked**, causing a mismatch between what the command expects as its
  incoming subject and what's actually passed.
- **TypeScript type declarations for the custom command
  (`Cypress.Chainable` interface augmentation) weren't updated to match
  a change in what the command returns**, so the compiler still thinks
  the old return type is being chained even though the runtime behavior
  changed.
- **A custom command wraps another Cypress command without returning its
  result**, silently breaking the chain by returning `undefined` instead
  of forwarding the wrapped command's chainable.

## Diagnose

1. Check the custom command's implementation for what it actually
   returns -- confirm every code path either returns a Cypress
   chainable (typically by returning the result of the last Cypress
   command called inside it) or is intentionally a terminal command.
2. Check the `prevSubject` configuration in `Cypress.Commands.add()`
   against how the command is actually called in tests (as a
   standalone command vs. chained off a previous subject).
3. For TypeScript setups, check the command's type declaration
   (usually in a `cypress.d.ts` or similar) against the actual runtime
   return type -- a stale type declaration can mask or produce
   misleading errors independent of the runtime behavior.
4. Add a `.then((subject) => { cy.log(String(subject)) })` immediately
   after the custom command in a failing test to directly inspect what
   subject is actually being passed through at runtime.

## Fix

Make sure every custom command explicitly returns the Cypress chainable
it intends to pass forward -- typically by returning the result of the
last `cy.` command invoked inside the custom command's implementation,
rather than letting the function's return value be implicit/undefined.
Set `prevSubject` deliberately and consistently with how the command is
actually meant to be called (standalone vs. chained), and keep the
TypeScript declaration for the command in sync with any change to its
actual return type as part of the same change, not as an afterthought.

## Pitfalls

Don't work around a chainability bug by inserting extra `cy.wrap()` calls
at every call site that uses the custom command -- that treats the
symptom at each usage site instead of fixing the command definition once,
and every new call site risks reintroducing the same workaround
inconsistently. Also don't ignore a TypeScript error on a Cypress chain
by casting to `any` -- it usually indicates a genuine mismatch between
the command's declared and actual behavior that will also confuse the
next person who chains off it.

## Verify

Write (or update) a test that chains a `.then()` or a further assertion
directly off the custom command and confirm it receives the correct,
expected subject at runtime. For TypeScript setups, confirm the command
compiles without needing an `any` cast anywhere it's used, and that the
inferred type of the chained subject matches what the command's
implementation actually returns.
