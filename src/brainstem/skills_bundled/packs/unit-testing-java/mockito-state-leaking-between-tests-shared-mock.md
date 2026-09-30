---
name: mockito-state-leaking-between-tests-shared-mock
description: A test passes or fails differently depending on test execution order because a Mockito mock's stubs or invocation history carried over from a previous test.
triggers: ["test passes alone but fails in suite", "mock state leaking between tests", "test order dependent failure JUnit", "verify counts wrong invocations from other test"]
permissions: ["READ"]
---

## Symptom
A test fails only when run as part of the full suite, but passes when run in isolation (or vice versa). Typical signs: `verify(mock, times(1))` reports 2+ invocations, or a stub returns a value configured by a *different* test method, or a test that never explicitly stubs a method still gets a non-default return value.

## Likely causes
1. **The mock field is created once per test class instead of once per test method.** If `@Mock` fields are initialized in a `@BeforeAll`/static block, or the mock is a `static` field, or it's built once in the constructor of a class using `TestInstance.Lifecycle.PER_CLASS`, the same mock instance -- with all its accumulated stubbing and invocation history -- is reused across every test method in the class.
2. **A shared base test class stubs a mock in its own `@BeforeEach` and subclasses add more stubbing without resetting**, so invocation counts recorded by the base class's setup call get counted alongside the subclass test's own calls.
3. **`Mockito.reset(mock)` or a fresh mock isn't happening between tests**, often because someone manually constructs mocks in a `@BeforeAll` "for performance" instead of trusting `@ExtendWith(MockitoExtension.class)` (which creates fresh mocks per test method by default under the normal per-method test lifecycle).
4. **Static state elsewhere** (a singleton, a static mutable field in the class under test) that a mock's stubbed method feeds into, so even fresh mocks per test can't fully isolate behavior if the object under test caches results in a static field across tests.

## Diagnose
1. Run the failing test alone: `mvn test -Dtest=OrderServiceTest#placesOrderSuccessfully` (or Gradle equivalent). If it passes alone but fails in the full class/suite run, order-dependence is confirmed.
2. Check the JUnit 5 test instance lifecycle: look for `@TestInstance(Lifecycle.PER_CLASS)` on the class. This changes JUnit's default of creating a new test instance per method, which combined with a mock field set once in the constructor or `@BeforeAll` produces mock reuse.
3. Grep the test class and any parent class for `@BeforeAll` bodies that call `mock(...)`, `when(...)`, or otherwise touch a mock -- setup that belongs in `@BeforeEach` is the most common culprit.
4. Add a temporary assertion at the top of the failing test: `verifyNoInteractions(theMock);` -- if this fails, the mock already has recorded interactions before this test even started, proving leakage.

## Fix
Let Mockito create a fresh mock per test method rather than trying to manually reset a long-lived one -- this is the default behavior with `@ExtendWith(MockitoExtension.class)` and the default (`PER_METHOD`) `TestInstance.Lifecycle`, so the fix is usually to remove whatever opted out of that default:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock private PaymentGateway paymentGateway; // fresh instance injected before EACH test method

    @BeforeEach
    void setUp() {
        // per-test stubbing here, not @BeforeAll
        lenient().when(paymentGateway.isAvailable()).thenReturn(true);
    }
}
```

If a genuinely expensive shared fixture forces `PER_CLASS` lifecycle for other reasons, explicitly call `Mockito.reset(mock)` in `@BeforeEach` to clear stubbing and invocation history -- but treat this as a fallback, not the default strategy, since `reset()` also silently discards `verifyNoMoreInteractions` intent from earlier in a test if misplaced.

## Pitfalls
`Mockito.reset()` is often flagged as a design smell by the Mockito team itself: needing to reset a mock mid-test usually means the test method is doing too much (testing multiple scenarios in one method) rather than the mock lifecycle being wrong. Prefer splitting the test into smaller methods with fresh per-method mocks over sprinkling `reset()` calls to patch over one large test.

## Verify
Run the full test class twice in a row (`mvn test -Dtest=OrderServiceTest` then re-run without `mvn clean`) and also run it with methods reordered -- JUnit 5 supports `@TestMethodOrder(MethodOrderer.Random.class)` temporarily -- to confirm results are identical regardless of execution order.
