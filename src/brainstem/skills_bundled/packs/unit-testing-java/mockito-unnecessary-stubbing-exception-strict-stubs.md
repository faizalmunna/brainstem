---
name: mockito-unnecessary-stubbing-exception-strict-stubs
description: A test fails with UnnecessaryStubbingException even though the stubbing looks correct because Mockito's strict stubbing detected an unused when() call.
triggers: ["UnnecessaryStubbingException", "Mockito strict stubs unused stubbing", "stubbing argument mismatch strict", "PotentialStubbingProblem"]
permissions: ["READ"]
---

## Symptom
A test that previously passed starts failing with `org.mockito.exceptions.misusing.UnnecessaryStubbingException: Unnecessary stubbings detected` at the end of the run, listing a `when(...)` line that looks like it should clearly be used by the code under test. This often appears right after adopting `@ExtendWith(MockitoExtension.class)` on a test class that previously used manual `MockitoAnnotations.openMocks`, since the extension enables Mockito's strict stubbing by default while manual initialization historically didn't.

## Likely causes
1. **A stub is set up in a shared `@BeforeEach` "for convenience" but only some test methods in the class actually exercise the code path that calls it** -- `MockitoExtension`'s default strictness (`STRICT_STUBS`) flags any stub that's never invoked by the end of the test method as unnecessary, per test method, not per class.
2. **The stubbed method is called with different arguments than the stub expects**, so Mockito never matches the stub to any real invocation -- the method *was* called, just not with arguments matching the `when(...)` clause, which strict stubbing reports as unnecessary stubbing rather than a matcher mismatch (this is subtly different from `PotentialStubbingProblem`, which fires mid-test when an invocation almost-but-not-quite matches an existing stub).
3. **A refactor removed the code path that used to call the stubbed method**, but the test's setup code stubbing it wasn't cleaned up -- the exception is doing its job correctly here, surfacing genuinely dead test setup.
4. **The stub is on a mock that's only used by some branches of an `if`/`switch` in the code under test, and the specific test method exercises a different branch** than the one the shared setup anticipated.

## Diagnose
1. Read the exception message carefully -- it names the exact `when(...)` call site (file and line) that was never satisfied.
2. Check whether that stub lives in `@BeforeEach` (shared across all test methods in the class) versus inside the specific failing test method -- shared setup stubs are the most common source since not every test method needs every stub.
3. For the specific failing test method, trace whether the code under test actually calls the stubbed method at all in that scenario, and if it does, compare the exact arguments passed at runtime (add a temporary `System.out.println` in a `doAnswer`) against the matcher/arguments used in the `when(...)` clause.
4. Check whether this test class recently moved from manual `MockitoAnnotations.openMocks()` to `@ExtendWith(MockitoExtension.class)` -- the extension defaults to strict stubbing while manual init defaults to lenient, so this exception can appear as a side effect of an unrelated "modernization" change, not a real new bug.

## Fix
For a stub that's only relevant to some test methods, move it out of shared `@BeforeEach` and into just the test methods that need it -- this is usually the right fix since it also makes each test's actual dependencies clearer to a reader:

```java
@ExtendWith(MockitoExtension.class)
class PricingServiceTest {
    @Mock private DiscountRepository discountRepository;
    @InjectMocks private PricingService pricingService;

    @Test
    void appliesBulkDiscountWhenEligible() {
        when(discountRepository.findBulkDiscount(any())).thenReturn(TEN_PERCENT);
        // ... this test actually exercises the bulk-discount path
    }

    @Test
    void returnsFullPriceWhenNoDiscountConfigured() {
        // No stubbing needed here -- default mock behavior (empty/null) is correct
        // for this scenario, so nothing is stubbed unnecessarily.
    }
}
```

When a stub genuinely is shared setup used by most-but-not-all tests, and moving it per-method would be repetitive, mark it `lenient()` explicitly to opt that specific stub out of strict-stubbing checks rather than disabling strictness for the whole class:

```java
@BeforeEach
void setUp() {
    lenient().when(discountRepository.isServiceAvailable()).thenReturn(true);
}
```

## Pitfalls
Don't reach for `@MockitoSettings(strictness = Strictness.LENIENT)` on the whole class as a first response to this exception -- that disables a genuinely useful signal (dead test setup, argument mismatches) for every test in the class, not just the one causing friction right now. Scope leniency to the specific stub with `lenient()` so the rest of the class keeps the safety net.

## Verify
After moving or marking the stub, run the full test class and confirm zero `UnnecessaryStubbingException`s, then deliberately break the code under test's call to the stubbed method (comment it out) and confirm the *specific* test that needs it now fails with a meaningful assertion error -- proving the stub is load-bearing for that test rather than just quietly tolerated.
