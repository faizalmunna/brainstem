---
name: autowired-field-null-new-instance
description: Diagnose an @Autowired dependency that is always null at runtime because the enclosing class was created with new instead of resolved by Spring.
triggers: ["autowired field is null", "nullpointerexception on autowired service", "dependency injection not working spring", "autowired null in filter", "new keyword spring bean null"]
permissions: ["READ"]
---

## Symptom
A field annotated `@Autowired` is `null` whenever it's accessed, causing
a `NullPointerException`, even though the same dependency is correctly
injected and works fine everywhere else in the application. The class
containing the `@Autowired` field compiles fine and the bean it depends
on is confirmed to exist and be correctly configured elsewhere -- the
problem is isolated to one specific class or one specific code path.

## Likely causes
1. **The object was instantiated with `new SomeClass()` directly** in
   application code, a factory, a static utility, or a servlet
   `Filter`/`Listener` -- Spring's dependency injection only runs on
   objects it constructs itself (beans in its `ApplicationContext`).
   An object created with `new` is invisible to the container, so
   `@Autowired` fields on it are simply never populated; this is by far
   the most common cause.
2. **The class is instantiated implicitly by a non-Spring framework
   hook** -- a JAX-RS provider, a JPA `AttributeConverter`, a custom
   `HttpSessionListener`, a Jackson `Deserializer`, or any SPI that the
   *framework* (not Spring) instantiates via reflection or a no-arg
   constructor, bypassing Spring entirely even though the class lives in
   a Spring-managed codebase.
3. **The field is accessed too early in the bean lifecycle** -- inside a
   constructor, or in field initializers that run before Spring has
   finished dependency injection (which happens after construction).
   This looks identical to "always null" but is actually a lifecycle
   ordering issue, not a missing-injection issue, and needs a different
   fix (`@PostConstruct` instead of manual bean lookup).
4. **The class is annotated for component scanning but the scan doesn't
   reach it** -- wrong package relative to `@SpringBootApplication`'s
   base package, or excluded by a custom `@ComponentScan` filter -- so
   the bean itself was never registered, which also manifests as
   downstream `@Autowired` fields *depending on it* being null, one
   level removed from the actual problem class.

## Diagnose
- Search for `new ClassName(` across the codebase for the exact class
  whose `@Autowired` field is null -- if any call site constructs it
  directly instead of obtaining it from Spring (constructor injection
  elsewhere, `@Autowired` field on a *caller*, or context lookup), that
  confirms cause 1.
- Check whether the class is registered as a bean at all: log
  `context.getBeanNamesForType(SomeClass.class)` at startup, or check
  `ApplicationContext.containsBean(...)`; an empty result means it's
  never a managed bean regardless of the `new` question.
- If the class is instantiated by a non-Spring framework SPI, check that
  framework's documentation for its Spring integration hook -- most
  (JAX-RS, Jackson, servlet API) have one, but it must be wired
  explicitly and isn't automatic just because Spring is also on the
  classpath.
- Add a log statement or breakpoint at the very top of the constructor
  and compare its timing against when the null field is first accessed
  -- if the access happens inside the constructor itself, that's a
  lifecycle-ordering issue (cause 3), not a missing-bean issue.

## Fix
The correct fix depends on which cause diagnosis confirmed, but the
underlying principle is the same: **anything needing Spring-managed
dependencies must itself be constructed by Spring**, so the fix is
always to route object creation through the container rather than to
work around a null field after the fact:
- If application code is constructing it with `new`, change that call
  site to instead inject the object as a proper collaborator bean
  (constructor injection into whatever *needs* it) rather than
  constructing it ad hoc.
- If a non-Spring framework instantiates it, use that framework's
  Spring-aware integration (e.g. `SpringBeanAutowiringSupport` for
  legacy servlet API classes, or a framework-specific `@Autowired`
  bridge) so the container performs injection on the framework-created
  instance after construction.
- If it's a lifecycle-ordering problem, move logic that depends on
  injected fields out of the constructor and into a `@PostConstruct`
  method, which Spring guarantees runs only after all injection is
  complete.

## Pitfalls
- Reaching for a static `ApplicationContext` holder
  (`ApplicationContextProvider.getBean(...)`) to manually fetch the
  dependency inside the `new`-constructed object is a working-but-
  fragile shortcut: it hides the real dependency graph, breaks in unit
  tests that don't bootstrap a full context, and reintroduces the same
  bug if the static holder itself isn't initialized yet at the point of
  use -- prefer fixing the construction path over papering over it with
  a service locator.
- Assuming "it's null so DI is broken globally" and adding defensive
  null checks everywhere the field is used treats the symptom instead of
  the cause, and hides the actual bug (an object escaping container
  management) behind code that now silently no-ops instead of failing
  loudly.

## Verify
Add an assertion or a startup check that the class in question is only
ever obtained via `ApplicationContext.getBean(...)` or constructor
injection -- e.g. a unit test that loads the Spring context and asserts
`context.getBean(SomeClass.class).getDependency()` is non-null -- and
confirm the original `new` call site (or non-Spring instantiation path)
no longer exists by re-running the grep for `new ClassName(` and finding
no remaining application-code matches.
