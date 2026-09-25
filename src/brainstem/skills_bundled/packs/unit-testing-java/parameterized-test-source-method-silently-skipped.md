---
name: parameterized-test-source-method-silently-skipped
description: A JUnit 5 parameterized test using MethodSource or CsvSource shows as skipped or reports zero invocations instead of failing loudly when the source is misconfigured.
triggers: ["ParameterizedTest shows 0 invocations", "MethodSource not found", "parameterized test skipped silently", "static method required for MethodSource"]
permissions: ["READ"]
---

## Symptom
A `@ParameterizedTest` method with `@MethodSource("provideArgs")` either doesn't appear as run at all in the test report, appears greyed-out/skipped in the IDE, or throws `org.junit.platform.commons.JUnitException: Could not find factory method` -- and in some CI setups this gets swallowed into an overall "0 tests failed" green build because the test never actually executed rather than executing and failing.

## Likely causes
1. **The `@MethodSource` factory method isn't `static`.** JUnit 5 requires factory methods referenced by `@MethodSource` to be static unless the test class is annotated with `@TestInstance(Lifecycle.PER_CLASS)` -- an instance method silently fails to resolve, and depending on JUnit/Surefire version this surfaces as an error, a skip, or (worst case) a build that doesn't fail the pipeline.
2. **The method name string in `@MethodSource("provideArgs")` doesn't exactly match the actual method name**, often after a rename/refactor where the IDE updated the method but not the string literal (string literals aren't tracked by refactoring tools the way method references are).
3. **The factory method's visibility is too restrictive** (`private` when the JUnit version/setup expects at least package-private, or vice versa depending on whether it's in the same class or an external `@ArgumentsSource` class) -- this varies by JUnit Jupiter version, so what worked in one version can silently stop resolving after an upgrade.
4. **`@CsvSource`/`@ValueSource` data doesn't match the method's declared parameter types or count** -- e.g. providing 3 CSV columns to a method expecting 2 parameters -- which can cause JUnit to report an initialization error for that specific invocation while other invocations from the same source still run, making it look like "some" of the parameterized cases were silently dropped.
5. **Missing `@ParameterizedTest` entirely while keeping `@Test` alongside `@MethodSource`** -- copy-pasting a parameterized test template but forgetting to swap the annotation means JUnit treats it as a plain `@Test` and ignores the source annotation, running the method once with no parameters (which then fails to compile if parameters are declared, or silently runs a no-arg version if refactored oddly).

## Diagnose
1. Run the test class with verbose output (`mvn test -Dtest=TheClass -Dsurefire.printSummary=true` or check the IDE's test run panel) and look specifically for the test method's expected multiple invocations (e.g. "provideArgs(...) [1]", "[2]") -- if only the method name shows with no numbered invocations, the source didn't resolve.
2. Check the factory method's modifiers: is it `static`? Is the class `@TestInstance(Lifecycle.PER_CLASS)`? These two must be consistent (non-static factory method requires per-class lifecycle).
3. Search for the exact string passed to `@MethodSource(...)` and confirm it matches a real method name in the class via find-usages or a direct text search -- a silent typo here is extremely common after refactors.
4. Check the JUnit Jupiter version in use (`junit-jupiter-params` artifact) against the parameter count/types expected by `@CsvSource` rows -- a mismatch often throws `ParameterResolutionException` naming the specific row index, which pinpoints exactly which case is malformed.
5. Confirm `@ParameterizedTest` (not `@Test`) is actually present on the method -- easy to miss visually since both annotations look similar at a glance.

## Fix
Make the factory method static (the common case, since most test classes use the JUnit 5 default per-method lifecycle) and reference it precisely:

```java
@ParameterizedTest
@MethodSource("provideDiscountScenarios")
void appliesCorrectDiscount(int quantity, BigDecimal expectedDiscount) {
    assertEquals(expectedDiscount, pricingService.discountFor(quantity));
}

private static Stream<Arguments> provideDiscountScenarios() {
    return Stream.of(
        Arguments.of(1, BigDecimal.ZERO),
        Arguments.of(10, new BigDecimal("5.00")),
        Arguments.of(100, new BigDecimal("50.00"))
    );
}
```

If sharing expensive per-class state genuinely requires `@TestInstance(Lifecycle.PER_CLASS)`, the factory method can then be non-static -- but that's a deliberate tradeoff (affects mock/field lifecycle across the whole class, see the mock-state-leaking skill in this pack) and should be chosen for that reason, not as an accidental side effect of a parameterized test not being static.

## Pitfalls
Don't blanket-annotate every parameterized test's source method as `static` just to make an error go away without understanding why -- if the class already relies on `@TestInstance(Lifecycle.PER_CLASS)` for a different reason (e.g. an expensive shared `@BeforeAll` fixture using instance fields), forcing the method static may compile fine but signals a design inconsistency worth double-checking, since per-class lifecycle exists precisely to allow non-static setup.

## Verify
Run the specific parameterized test method and confirm the test report shows the expected number of distinct invocations (matching the number of rows/arguments provided), not just one aggregate pass/fail -- e.g. `mvn test -Dtest=PricingServiceTest#appliesCorrectDiscount` should list `[1] 1, 0`, `[2] 10, 5.00`, `[3] 100, 50.00` as separate results.
