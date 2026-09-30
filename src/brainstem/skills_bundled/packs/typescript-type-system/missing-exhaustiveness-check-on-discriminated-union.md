---
name: missing-exhaustiveness-check-on-discriminated-union
description: Adding a new member to a discriminated union does not produce a compile error at a switch statement that handles every existing case but omits the new one.
triggers: ["switch statement not catching new union case", "added enum value but no compile error", "exhaustiveness check not working typescript", "forgot to handle new case in switch", "assertNever pattern"]
permissions: ["READ"]
---

## Symptom
A discriminated union (`type Action = { type: 'add'; ... } | { type:
'remove'; ... }`) is handled with a `switch (action.type)` covering every
current case. Later, a teammate adds a third variant to the union. The
`switch` statement is not updated to handle it, and the code compiles and
deploys without any error -- the new case simply falls through to
whatever the `switch` does by default (often nothing, or an incorrect
fallback branch), and the gap is only discovered when that new action
type silently does nothing in production.

## Likely causes
- **The `switch` has no `default` case at all**, so TypeScript has no
  location to attach an exhaustiveness check to -- without a `default`
  branch, the compiler simply stops checking once known cases are listed;
  it doesn't proactively warn "you didn't handle everything" on its own.
- **The `switch` has a `default` case, but it does something silently
  reasonable-looking** (returns `null`, breaks with no action, logs and
  continues) instead of asserting the case is unreachable -- a
  do-nothing default doesn't error at compile time when a new member
  reaches it, it just runs the do-nothing branch at runtime.
- **The function's return type is inferred rather than explicitly
  annotated**, so even if every current branch returns a value, adding a
  new unhandled case that falls through to `undefined` doesn't produce a
  return-type mismatch -- TypeScript just infers a wider return type that
  happens to include `undefined`, instead of flagging the gap.
- **The union itself isn't actually a proper discriminated union** -- the
  common tag property has an inconsistent name or type across members
  (one variant's tag is a plain `string` instead of a literal type), which
  prevents `never`-based exhaustiveness checking from working at all,
  since TypeScript can't narrow the switch cases down to `never` in the
  `default` branch if the discriminant isn't a literal union.

## Diagnose
1. Search for `switch` statements over the union's discriminant property
   and check each one for a `default` case -- absence of `default` is the
   most common root cause and is a pure text search away
   (`grep -n "switch (" ` on files importing the union type).
2. Where a `default` exists, check what it does. If it's anything other
   than passing the value to a function typed to accept `never`, it's not
   actually enforcing exhaustiveness even though it looks defensive.
3. Confirm the union's discriminant is a true discriminated union: hover
   the property's type on each member and confirm each is a distinct
   string/number *literal* type, not a widened `string`/`number` -- if any
   member's tag was declared without `as const` or an explicit literal
   type annotation, exhaustiveness narrowing silently breaks.
4. Add a throwaway new union member locally and see whether any `switch`
   in the codebase currently fails to compile because of it -- if none do,
   exhaustiveness checking isn't wired up anywhere for that union, which
   is the actual scope of the gap, not just the one file you started from.

## Fix
Add a `default` case to every `switch` over the union's discriminant that
calls a small shared `assertNever` helper: `function assertNever(x:
never): never { throw new Error('Unhandled case: ' + JSON.stringify(x));
}`, and call it as `default: return assertNever(action);` (or without
`return` if the function's control flow doesn't require a value). This
works because inside the `default` branch, after every real case has been
handled, TypeScript narrows the switched value's type to `never` -- if a
new union member is added and a case for it is missing, that member's
type now flows into the `default` branch as something other than `never`,
which fails to satisfy `assertNever`'s `never` parameter and produces a
compile error pointing at exactly that `switch`. Apply this consistently
to every `switch` (and equivalent `if`/`else if` chain, using the same
pattern at the end) over the same discriminated union, since exhaustiveness
protection is per-switch, not automatic project-wide.

## Pitfalls
Don't implement `assertNever` to just `return null` or log a warning
instead of narrowing to `never` and throwing/erroring -- a "soft" default
case defeats the entire mechanism, because it no longer requires the
argument type to be `never`, so it stops being a compile-time check and
becomes exactly the silent do-nothing default this skill is trying to
eliminate. Also watch for the exhaustiveness check being defeated by
casting the discriminant to `any`/`string` upstream (e.g. an API response
typed as `string` instead of the literal union) before the `switch` --
the check only works if the discriminant retains its literal-union type
all the way to the `switch`.

## Verify
Add a new dummy member to the union type, run `tsc --noEmit`, and confirm
every `switch` over that union that lacks a case for the new member now
fails to compile with an error referencing the `assertNever`/`never`
parameter -- if any relevant `switch` stays silent, its `default` case
still isn't wired to the `never`-narrowing pattern and needs the same fix.
Then remove the dummy member before committing.
