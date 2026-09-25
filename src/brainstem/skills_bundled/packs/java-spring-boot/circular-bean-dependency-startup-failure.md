---
name: circular-bean-dependency-startup-failure
description: Diagnose a Spring Boot application that fails to start with BeanCurrentlyInCreationException or produces a bean that is only partially initialized.
triggers: ["beancurrentlyincreationexception", "circular dependency spring", "unsatisfied dependency circular reference", "requested bean is currently in creation", "spring boot fails to start with cycle"]
permissions: ["READ"]
---

## Symptom
The application either fails to start entirely with
`BeanCurrentlyInCreationException` (or
`UnsatisfiedDependencyException` wrapping it) naming two or more beans
that depend on each other, or -- more insidiously -- it *does* start
(because setter/field injection allowed Spring to paper over the cycle)
but one of the beans in the cycle ends up holding a reference to a
proxy or an incompletely configured instance of the other, causing
mysterious `NullPointerException`s or stale behavior later at runtime
rather than at startup.

## Likely causes
1. **A genuine circular dependency in the design** -- Bean A's
   constructor needs Bean B, and Bean B's constructor needs Bean A.
   With constructor injection this is always fatal at startup, because
   Spring cannot construct either without the other already existing.
2. **A cycle that "worked" before an AOP proxy was introduced** --
   adding `@Transactional`, `@Cacheable`, `@Async`, or any other
   proxied annotation to one of the beans in a previously-fine field/
   setter-injection cycle changes bean creation order/proxying enough to
   suddenly surface `BeanCurrentlyInCreationException` where it didn't
   before, because the proxy needs the target fully created first.
3. **An indirect cycle through configuration classes** -- `@Configuration`
   class A has a `@Bean` method calling a service that is, transitively,
   built from a `@Bean` method in `@Configuration` class B which itself
   depends on something from class A -- much harder to spot than a
   direct two-class cycle because it's hidden behind `@Bean` method
   calls rather than field references.
4. **A cycle intentionally "solved" with `@Lazy` on one side**, but the
   lazy proxy is then stored and used past its intended narrow purpose,
   masking a design problem rather than fixing it -- works at startup,
   but the underlying circular ownership is still there and shows up as
   confusing behavior under refactoring later.

## Diagnose
- Read the full `BeanCurrentlyInCreationException` chain in the startup
  log -- Spring prints the exact cycle of bean names it detected
  (`... which is currently in creation ...`), so the cycle members are
  already named, no guessing needed.
- If the app *starts* but behaves wrong, check whether the beans in
  suspicion use field/setter injection (`@Autowired` on a field or
  setter) rather than constructor injection -- field injection is what
  allows Spring to silently tolerate a cycle by injecting a not-yet-fully-
  initialized reference.
- Search for `@Bean` methods that call other `@Bean` methods across
  different `@Configuration` classes, and trace whether that call graph
  loops back to the configuration class that started it.
- Temporarily set `spring.main.allow-circular-references=false` (the
  Spring Boot 2.6+ default) if it had been overridden to `true` --
  this is the fastest way to force a hidden cycle to surface as a hard
  startup failure instead of continuing to run silently.

## Fix
The reasoned fix is to break the cycle at the design level, not to paper
over it with `@Lazy`:
- **Extract the shared responsibility into a third bean** that both A
  and B depend on one-directionally -- this is almost always the right
  fix when the "cycle" is really two services that both need a piece of
  logic that belongs in neither of them.
- **Invert one dependency to an event or callback** -- if A needs to
  notify B of something rather than call it synchronously for a return
  value, publishing an application event (`ApplicationEventPublisher`)
  that B listens for removes the compile-time/wiring-time dependency
  entirely.
- Only if the cycle is genuinely unavoidable and narrow (e.g. a
  bootstrapping concern), use `@Lazy` on the constructor parameter for
  *one* side, which makes Spring inject a proxy that defers the actual
  lookup until first use -- but treat this as an explicit, documented
  exception, not the default way to resolve cycles, since it hides
  rather than resolves the circular ownership.

## Pitfalls
- Switching from constructor injection to field injection specifically
  to "make the cycle go away" trades a loud startup failure for a silent
  partial-initialization bug that surfaces later and is much harder to
  debug -- it is not a fix, it's deferring the same problem to runtime.
- Reaching for `allow-circular-references=true` globally re-enables the
  old permissive behavior for the *entire application*, hiding future
  accidental cycles introduced by unrelated changes, not just the one
  currently being debugged.

## Verify
After restructuring, start the application with default Spring Boot
settings (`allow-circular-references` at its default `false`) and
confirm it starts cleanly with no `BeanCurrentlyInCreationException`;
additionally write a unit test that constructs the previously-cyclic
beans directly (not through the full context) to confirm each one is
independently constructible without needing the other pre-existing.
