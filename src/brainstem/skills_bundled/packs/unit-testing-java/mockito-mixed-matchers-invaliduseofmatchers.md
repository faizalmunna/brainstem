---
name: mockito-mixed-matchers-invaliduseofmatchers
description: Stubbing or verifying a Mockito call throws InvalidUseOfMatchersException because argument matchers were mixed with raw literal values.
triggers: ["InvalidUseOfMatchersException", "mixing any() with real value Mockito", "invalid use of argument matchers", "Mockito eq and any together error"]
permissions: ["READ"]
---

## Symptom
A stub or verify call like `when(repo.save(any(User.class), "audit-tag")).thenReturn(saved);` throws `org.mockito.exceptions.misusing.InvalidUseOfMatchersException: Invalid use of argument matchers! 2 matchers expected, 1 recorded`. The stack trace points at the stub line itself, before the test logic even runs, which confuses people into thinking the method signature is wrong.

## Likely causes
1. **A matcher (`any()`, `anyString()`, `eq()`, etc.) is combined with a plain literal or variable in the same call.** Mockito's matcher recording is all-or-nothing per invocation: once *any* argument in the call uses a matcher, *every* argument must use a matcher, including ones that should just be exact values.
2. **Copy-pasted stub from a call with a different arity** -- someone changed the method signature (added/removed a parameter) and updated the matcher count in one call but not a sibling call, or vice versa, so matcher count no longer lines up with the real parameter count.
3. **Using `eq()` inconsistently across an argument list** -- forgetting that a literal like `"audit-tag"` needs to become `eq("audit-tag")` the moment any sibling argument becomes `any(...)`, especially common when a test is incrementally loosened (one hardcoded arg replaced with `any()` to reduce brittleness) without touching the rest of the line.
4. **Matchers used outside of a stub/verify context**, e.g. calling `any(User.class)` directly to build a real argument passed elsewhere in the test (not inside `when(...)` or `verify(...)`) -- Mockito matchers register onto a thread-local stack and leak into the *next* mock call, causing an unrelated subsequent stub to throw this exception.

## Diagnose
1. Read the exact line the stack trace names and count matcher calls (`any`, `anyX`, `eq`, `argThat`, etc.) versus plain arguments in that single method call.
2. If the counts already look equal, check the line(s) *before* it in the same test for a stray matcher call that wasn't wrapped in `when(...)`/`verify(...)` -- that leaks a pending matcher onto Mockito's stack and throws on the *next* mock interaction, not the one that actually misused a matcher.
3. Diff against the real method signature (open the mocked interface/class) to confirm the parameter count assumed by the test still matches production code -- a recent signature change is a common trigger.
4. Search the test file for any raw literal sitting next to a matcher in the same parentheses, e.g. `verify(mock).method(eq(id), "literal")` -- that literal is the bug.

## Fix
The pattern: if one argument in a call needs a matcher, wrap every argument in that call with a matcher -- use `eq(value)` for anything that should match exactly:

```java
// Wrong: mixes any() with a raw literal
when(repo.save(any(User.class), "audit-tag")).thenReturn(saved);

// Correct: every argument is a matcher
when(repo.save(any(User.class), eq("audit-tag"))).thenReturn(saved);
```

Applying this consistently means treating "add a matcher" as an operation on the whole call, not a single argument -- when loosening one parameter, immediately wrap the rest in `eq()` in the same edit rather than leaving them bare.

## Pitfalls
Don't reach for `ArgumentMatchers.anyString()`/`any()` everywhere just to make the compiler/runtime stop complaining if the test actually cares about a specific value -- that silently weakens the test's assertion power (it'll pass even if the wrong string is passed). Use `eq()` to keep exactness where the test's intent requires it, and reserve loose matchers for arguments the test genuinely doesn't care about.

## Verify
Run the test and confirm it fails meaningfully when the production code is deliberately mutated (e.g. temporarily hardcode a different literal being passed to the mocked method) -- if the test still passes after that mutation, the matcher was too loose and defeated the point of asserting that argument at all.
