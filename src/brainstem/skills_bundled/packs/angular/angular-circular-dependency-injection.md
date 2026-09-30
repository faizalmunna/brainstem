---
name: angular-circular-dependency-injection
description: Diagnose a circular dependency injection error thrown at app startup between two services that inject each other.
triggers: ["circular dependency angular", "NG0200 circular dependency detected", "maximum call stack size exceeded angular service", "two services injecting each other"]
permissions: ["READ"]
---

## Symptom
The app fails to bootstrap, throwing `NG0200: Circular dependency in DI
detected` (or, in some setups, a plain "Maximum call stack size exceeded")
with an error trace naming two services whose constructors each inject
the other.

## Likely causes
1. **Two services genuinely call each other's methods bidirectionally**
   (ServiceA calls ServiceB and ServiceB calls ServiceA), which usually
   signals overlapping responsibilities that should live in one place or
   a shared dependency.
2. **An indirect cycle through a chain**: ServiceA injects ServiceB, which
   injects ServiceC, which -- often through a barrel `index.ts`
   re-export or a shared base class -- ends up injecting ServiceA again
   without any single file looking obviously circular.
3. **A service injects itself indirectly** through an abstract base class
   or an injection token whose provider (via `useExisting`) resolves back
   to the same service.
4. **`forwardRef()` was already used to paper over a real cyclical
   design** (common in parent/child component communication patterns
   copy-pasted into a service-to-service context where it doesn't fit).

## Diagnose
- Read the DI error's printed injector chain carefully -- Angular lists
  the exact sequence of tokens it was resolving when it detected the
  cycle; that sequence is the cycle, not just a hint toward it.
- Sketch the dependency graph among the named services (which constructor
  injects which) -- a cycle of length 2 or 3 is usually visible
  immediately once written down, even when it wasn't obvious in code.
- Search the involved constructors for `forwardRef(() => X)` -- its
  presence means the cycle was already suspected and worked around
  rather than resolved at the design level.

## Fix
- Extract the behavior both services need into a third, lower-level
  service (or a plain injectable state/store) that both depend on in one
  direction only, breaking the cycle at its structural root instead of
  routing around it.
- Replace a direct method call from one service to the other with an
  event published on that shared lower-level service (a `Subject` the
  other service subscribes to), so neither needs a direct reference to
  the other.
- If a bidirectional reference is structurally unavoidable (a legitimate
  parent/child component communication case, not two peer services), use
  `forwardRef()` deliberately for that one direction plus `@Optional()`
  where the dependency might not be present -- but only after confirming
  the shared-dependency extraction above genuinely doesn't apply.

## Pitfalls
- Reaching for `forwardRef()` as the first fix without asking why the
  cycle exists just delays the failure from a clear bootstrap-time DI
  error to a confusing runtime "undefined is not a function" the first
  time the method is actually called.
- Merging the two services into one to make the error disappear removes
  the cycle but produces a monolith mixing unrelated responsibilities,
  making both harder to test in isolation -- prefer extracting the shared
  dependency instead of merging the two dependents.

## Verify
Restart the app and confirm bootstrap completes with no `NG0200` or stack
overflow; then exercise both services' original functionality
independently (not just that the app loads) to confirm neither lost
behavior in the refactor.
