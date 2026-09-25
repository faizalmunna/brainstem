---
name: junit5-lifecycle-annotation-wrong-scope
description: Setup or teardown code runs at the wrong frequency across a test class because BeforeAll, BeforeEach, AfterEach, or AfterAll was used for the wrong scope.
triggers: ["BeforeAll must be static error", "setup runs once instead of every test", "state carried over between test methods", "AfterAll not cleaning up resource"]
permissions: ["READ"]
---

## Symptom
Several distinct but related failures, all traceable to the same root category: (a) a test class fails to even start with `JUnitException: @BeforeAll method must be static`; (b) an expensive resource (e.g. a test container, a file, a connection) is unexpectedly recreated before every single test method when it was meant to be shared once for the whole class; or (c) a mutable object set up once in `@BeforeAll` accumulates changes across test methods because it wasn't meant to be class-scoped at all.

## Likely causes
1. **`@BeforeAll`/`@AfterAll` methods must be `static` under the default `PER_METHOD` test instance lifecycle**, because JUnit 5 creates a new test instance per method and needs a class-level (static) hook to run before any instance exists -- forgetting `static` throws immediately at class initialization, not at a specific test.
2. **Genuinely per-test setup was written in `@BeforeAll` "to save time,"** e.g. constructing a mutable domain object once and reusing it across test methods -- one test mutates it, and subsequent tests see that mutation instead of a clean starting state, producing order-dependent failures.
3. **Expensive, safely-shareable setup (e.g. spinning up a Testcontainers database) was written in `@BeforeEach`** instead of `@BeforeAll`, so it's needlessly recreated before every test method, massively slowing the suite for no correctness benefit.
4. **`@TestInstance(Lifecycle.PER_CLASS)` was added to allow non-static `@BeforeAll`, but the team didn't think through the side effect**: with `PER_CLASS`, a single test instance (and all its non-mock instance fields) is now shared across every test method in the class, which silently changes the semantics of any instance field that used to be freshly constructed per test under the default `PER_METHOD` lifecycle.
5. **`@AfterEach` cleanup is written assuming `@BeforeEach` state exists, but a test that throws during `@BeforeEach` itself skips straight to `@AfterEach`**, which then hits a `NullPointerException` trying to clean up a resource that was never created, obscuring the real failure (the original `@BeforeEach` exception gets suppressed/shadowed in some reporting setups).

## Diagnose
1. If the class fails at startup rather than at any specific test, read the exact JUnit exception -- `@BeforeAll method must be static` or `@AfterAll method must be static` names the exact problem and method.
2. For suspected shared-mutable-state issues, check what's initialized in `@BeforeAll` versus `@BeforeEach`: anything mutable that a test method modifies (adds to a list, sets a field) belongs in `@BeforeEach` unless the whole point is deliberate sharing.
3. For a suite that's slower than expected, check whether `@BeforeEach` contains anything that looks expensive (container startup, file I/O, network calls) that doesn't depend on per-test state -- that's a candidate to hoist to `@BeforeAll`.
4. Check for `@TestInstance(Lifecycle.PER_CLASS)` and read every instance field in the class -- with per-class lifecycle, ask for each field: "is it fine for this to be shared and potentially mutated across all test methods?" If not, that field needs re-initialization in `@BeforeEach` even under `PER_CLASS`.
5. Reproduce the `@AfterEach` NPE-on-cleanup case by deliberately breaking `@BeforeEach` (throw early) and confirming whether `@AfterEach` still runs and whether it null-checks before cleaning up.

## Fix
Match the annotation to the actual sharing intent, treating "does this need to be fresh per test?" as the deciding question:

```java
class OrderServiceIntegrationTest {
    // Expensive, safely shared, immutable-from-the-tests'-perspective: BeforeAll + static
    private static PostgreSQLContainer<?> database;

    @BeforeAll
    static void startDatabase() {
        database = new PostgreSQLContainer<>("postgres:16").withReuse(true);
        database.start();
    }

    // Cheap, and mutated per test: BeforeEach, non-static
    private OrderBuilder orderBuilder;

    @BeforeEach
    void freshFixture() {
        orderBuilder = new OrderBuilder(); // guarantees no state carries over between tests
    }

    @AfterEach
    void cleanUpOrders() {
        if (orderBuilder != null) { // defensive: BeforeEach may have thrown before assigning
            orderBuilder.clear();
        }
    }
}
```

The reasoning: `@BeforeAll`/`@AfterAll` are for cost amortization of things safe to share (read-only fixtures, expensive external resources), and require `static` under the default lifecycle because they run before any test instance exists. `@BeforeEach`/`@AfterEach` are for guaranteeing a clean, isolated starting state per test method -- default to these for anything mutable.

## Pitfalls
Adding `@TestInstance(Lifecycle.PER_CLASS)` purely to make a `@BeforeAll` method non-static (because it wants to call another instance method) is a common shortcut that quietly converts *every* instance field in the class to class-scoped sharing -- audit every field in the class before adopting `PER_CLASS`, not just the one that motivated the change.

## Verify
Run the test class with methods intentionally reordered (or use `@TestMethodOrder(MethodOrderer.Random.class)` temporarily) and confirm results don't change based on order -- this specifically catches state that was wrongly scoped to `@BeforeAll` when it should have been per-test `@BeforeEach` state.
