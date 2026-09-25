---
name: mockstatic-not-closed-leaks-across-tests
description: A static method mocked with Mockito.mockStatic continues returning the stubbed value in later, unrelated tests because the mock was never closed.
triggers: ["mockStatic leaking into other tests", "static mock still active in next test", "MockedStatic already registered exception", "Mockito static mock not closed"]
permissions: ["READ"]
---

## Symptom
A test uses `Mockito.mockStatic(SomeUtility.class)` to stub a static method and gets the expected result. But a completely unrelated test, run afterward in the same suite, unexpectedly gets the *stubbed* return value from that static method instead of the real one -- or the suite throws `org.mockito.exceptions.base.MockitoException: For SomeUtility, static mocking is already registered in the current thread`.

## Likely causes
1. **`mockStatic(...)` was called without a try-with-resources block and never explicitly `.close()`d.** `MockedStatic` registers itself as an active static stub on the current thread until closed; if the test method returns (or throws) before closing it, the stub stays active for whatever runs next on that same thread.
2. **An exception thrown mid-test skips the close call** because it was written as a plain local variable with a manual `.close()` at the end of the method body -- if an assertion fails or the code under test throws before reaching that line, `close()` never executes.
3. **Parallel test execution on the same JVM/thread pool** where `mockStatic` is thread-bound: if the test runner reuses threads across test classes (common with JUnit 5 parallel execution or certain Gradle worker configurations), a static mock opened on a thread in one test class can still be "active" when another test class's method happens to run on that same thread before the first one's cleanup runs.
4. **Nested or sequential `mockStatic` calls on the *same* class within one test class** without closing the first before opening a second -- Mockito only allows one active static mock per class per thread at a time, so the second call throws the "already registered" exception rather than silently overriding the first.

## Diagnose
1. Search the test file for `mockStatic(` and check whether it's inside a `try (MockedStatic<...> mocked = mockStatic(...)) { ... }` block. If it's assigned to a plain variable with `.close()` called manually later in the method, that's the leak risk.
2. Run the suspected leaking test in isolation, then run the whole class/suite -- if a downstream test only fails in the full run and the failure involves the same utility class's static method returning an unexpected value, that confirms leakage rather than an unrelated bug.
3. Check whether `close()` sits after any assertion or code that could throw -- assertions placed before the `close()` call in a non-try-with-resources setup mean any assertion failure skips cleanup.
4. If using parallel test execution, check the JUnit 5 config (`junit-platform.properties` for `junit.jupiter.execution.parallel.enabled=true`) -- static mocks and parallel execution require extra care since thread reuse is exactly what makes the leak visible.

## Fix
Always scope `MockedStatic` with try-with-resources so it's guaranteed to close even when the test body throws, tying its lifetime exactly to the block that needs the stub:

```java
@Test
void usesStubbedStaticUtility() {
    try (MockedStatic<SomeUtility> mockedUtility = Mockito.mockStatic(SomeUtility.class)) {
        mockedUtility.when(SomeUtility::currentTimestamp).thenReturn(FIXED_TIME);

        String result = classUnderTest.doSomethingThatCallsTheStatic();

        assertEquals("expected-with-fixed-time", result);
    } // MockedStatic.close() runs here automatically, even if an assertion above throws
}
```

The pattern generalizes: any Mockito resource implementing `AutoCloseable` (`MockedStatic`, `MockedConstruction`) should live inside try-with-resources scoped as tightly as possible around the specific test logic that needs the static stub, never held open for the whole test class or manually closed at the end of a method body.

## Pitfalls
Don't stub a static method for the entire test class in a shared `@BeforeEach` "to save typing" by opening a `MockedStatic` there and closing it in `@AfterEach` -- it technically works but widens the blast radius: any test method in the class that doesn't need the static stub still runs with it active, which can mask bugs in code paths that should be calling the *real* static method. Scope it per test method that actually needs it.

## Verify
Run the full test class (not just the individual test) and confirm no other test method's assertions about the same utility class change behavior. Additionally, add a later test method in the same file that calls the real (non-mocked) static method and confirm it returns the real value, not a previous test's stubbed one.
