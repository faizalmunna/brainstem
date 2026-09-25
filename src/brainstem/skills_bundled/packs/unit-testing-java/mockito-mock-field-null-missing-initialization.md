---
name: mockito-mock-field-null-missing-initialization
description: A field annotated with @Mock or @InjectMocks is null at test runtime, throwing NullPointerException before any stubbing runs.
triggers: ["@Mock field is null", "NullPointerException on mock in JUnit test", "InjectMocks not injecting mocks", "MockitoAnnotations.openMocks not called"]
permissions: ["READ"]
---

## Symptom
A test class declares `@Mock private SomeService someService;` and `@InjectMocks private SomeController controller;`, but the very first line of the test that touches `someService` throws a `NullPointerException`. Sometimes it's intermittent across a suite -- some test classes work fine, others don't -- which makes it look like a flaky test rather than a setup bug.

## Likely causes
1. **Mockito annotations were never processed.** `@Mock`/`@InjectMocks` are inert metadata unless something actually initializes them -- either `@ExtendWith(MockitoExtension.class)` on the class (JUnit 5) or a manual `MockitoAnnotations.openMocks(this)` call in a `@BeforeEach`. Without one of these, the fields stay `null` exactly like any other unassigned field.
2. **Mixed JUnit 4/5 artifacts.** The class uses `org.junit.Before` (JUnit 4) instead of `org.junit.jupiter.api.BeforeEach` (JUnit 5) while the rest of the project runs on JUnit 5, so the initialization method silently never executes because the JUnit 5 engine doesn't recognize the JUnit 4 annotation.
3. **`openMocks(this)` called on the wrong instance**, e.g. inside a static method, a helper class, or a `@BeforeAll` (static context) where `this` doesn't refer to the actual test instance being run -- common when someone extracts setup into a shared base class incorrectly.
4. **Field is declared but the test instantiates the object under test manually** (`new SomeController(new SomeServiceImpl())`) instead of relying on `@InjectMocks`, bypassing the mock entirely even though Mockito initialized it fine -- the NPE then comes from a *different* uninitialized collaborator inside that real object.

## Diagnose
1. Open the test class and check the class-level annotations: is `@ExtendWith(MockitoExtension.class)` present? If not, search for `MockitoAnnotations.openMocks` or the deprecated `initMocks` in a `@BeforeEach`/`@Before`.
2. Check the import of the lifecycle annotation: `import org.junit.Before;` vs `import org.junit.jupiter.api.BeforeEach;`. If the build uses `junit-jupiter` as the test engine and the class imports `org.junit.Before`, that method is dead code -- confirm by checking `pom.xml`/`build.gradle` for `junit-jupiter-engine` and the absence of `junit-vintage-engine`.
3. Add a temporary `System.out.println(someService)` (or a debugger breakpoint) right before the failing line to confirm the field is literally `null`, not just misbehaving.
4. Check any shared/base test class for `@BeforeAll` — Mockito field injection must happen per-instance in `@BeforeEach`/`@Before`, not once per class in a static `@BeforeAll`.

## Fix
Prefer `@ExtendWith(MockitoExtension.class)` (JUnit 5 + `mockito-junit-jupiter` dependency) over manual initialization -- it ties mock lifecycle to the JUnit engine so there's no separate step to forget:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock private PaymentGateway paymentGateway;
    @InjectMocks private OrderService orderService;
    // fields are guaranteed initialized before each test method
}
```

If the project is still on JUnit 4 or can't add the extension dependency, the manual fallback must run before every test, which means `@Before`/`@BeforeEach` (instance method, not static):

```java
@BeforeEach
void setUp() {
    MockitoAnnotations.openMocks(this);
}
```

The underlying pattern: Mockito needs an explicit trigger, once per test instance, to reflectively populate `@Mock`/`@Spy`/`@InjectMocks` fields. Pick exactly one mechanism (extension or manual call) and don't mix both, since duplicating initialization can mask which one is actually responsible when it breaks later.

## Pitfalls
Don't "fix" this by having the test manually `new` up the mock (`someService = mock(SomeService.class);`) while leaving the `@Mock` annotation in place -- now there are two different mock instances in play if `@InjectMocks` also tries to wire the annotated one, and stubbing one doesn't affect the other, producing a *different* confusing failure (`UnnecessaryStubbingException` or verification failures on the "wrong" mock).

## Verify
Run the single test class with `-Dtest=OrderServiceTest` (Maven) or `--tests OrderServiceTest` (Gradle) and confirm the mock field is non-null by asserting a stub actually takes effect, e.g. `when(paymentGateway.charge(any())).thenReturn(true);` followed by a call that depends on that stubbed value returning `true` rather than throwing.
