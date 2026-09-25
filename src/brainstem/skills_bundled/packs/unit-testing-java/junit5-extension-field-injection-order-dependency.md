---
name: junit5-extension-field-injection-order-dependency
description: A field set up by one JUnit 5 extension is null or stale when a second extension's callback runs, because extension execution order wasn't controlled.
triggers: ["extension order JUnit 5", "field null in BeforeEach across extensions", "RegisterExtension order matters", "multiple extends with dependency between them"]
permissions: ["READ"]
---

## Symptom
A test class combines two or more JUnit 5 extensions -- for example `@ExtendWith(MockitoExtension.class)` alongside a custom extension that reads an `@Mock` field to configure it further, or a `@RegisterExtension` field alongside `@ExtendWith`. One extension's `beforeEach` callback needs a value that another extension is supposed to have set up, but it reads `null` or a stale value, even though both extensions clearly ran (no exception about a missing extension).

## Likely causes
1. **Extension execution order isn't guaranteed by declaration order alone once both `@ExtendWith` (class-level) and `@RegisterExtension` (field-level) are mixed** -- JUnit 5 has documented but easy-to-forget rules: globally registered extensions run before locally declared ones, and `@RegisterExtension` fields run in the order they're declared, but interleaving with `@ExtendWith` from annotations doesn't follow simple top-to-bottom reading order of the source file.
2. **A custom extension's `beforeEach` runs before `MockitoExtension`'s `beforeEach` has populated `@Mock` fields**, so code in the custom extension that tries to call `Mockito.when(...)` on those fields gets a `NullPointerException` or operates on an uninitialized mock -- this happens because extension order in `@ExtendWith(A.class, B.class)` is the order they're listed, and it's easy to list a dependent extension before its dependency.
3. **A `@RegisterExtension` field depends on another `@RegisterExtension` field declared later in the same class** -- field order matters here, and reordering fields for readability (e.g. alphabetizing) can silently break an implicit ordering dependency nobody documented.
4. **Base class extensions and subclass extensions interact unexpectedly** -- a superclass's `@ExtendWith` runs its callbacks at a different point relative to a subclass's own `@RegisterExtension` field than intuition suggests, especially around `@BeforeEach` methods also being involved in the same base/subclass hierarchy.

## Diagnose
1. List every extension mechanism in play across the class and its superclasses: annotations (`@ExtendWith`), fields (`@RegisterExtension`), and any meta-annotations that bundle extensions together.
2. Add a `System.out.println` (or logging) at the very start of each custom extension's `beforeEach`/`beforeAll` callback, printing the extension's name and a timestamp/counter -- run the test and read the actual order extensions fired in, rather than assuming it matches source order.
3. Check the JUnit 5 user guide's extension ordering rules for the specific combination in use (`@ExtendWith` list order, "outside-in" for `beforeEach`, "inside-out" for `afterEach`, and how `@RegisterExtension` fields interleave) -- confirm which rule actually governs this case instead of guessing.
4. If a `@Mock` field is the value in question, temporarily add a null-check with a descriptive message at the top of the dependent extension's callback (`Objects.requireNonNull(mockField, "MockitoExtension has not run yet")`) to pinpoint exactly which callback fires too early.

## Fix
Where possible, avoid needing cross-extension ordering entirely -- move logic that depends on another extension's setup into the test's own `@BeforeEach` method, which is guaranteed by the JUnit 5 spec to run *after* all registered extensions' `beforeEach` callbacks:

```java
@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {
    @Mock private EmailClient emailClient;

    @BeforeEach
    void configureMock() {
        // Runs after MockitoExtension has populated @Mock fields --
        // safe to configure them here regardless of extension ordering rules.
        lenient().when(emailClient.isConnected()).thenReturn(true);
    }
}
```

When two custom extensions genuinely must run in a specific order relative to each other, make the dependency explicit rather than relying on declaration order: either combine them into a single extension that internally sequences the two pieces of setup, or use `@Order` on `@RegisterExtension` fields (supported since JUnit 5.8 via declaration order guarantees for same-type registration) and document why the order matters directly above the field.

## Pitfalls
Don't "solve" ordering issues by reordering `@ExtendWith(...)` arguments through trial and error until the test happens to pass -- without understanding *why* the new order works, the next unrelated change to the class (adding a field, upgrading JUnit) can silently reintroduce the bug. Document the ordering requirement with a comment citing the specific JUnit extension model rule being relied on.

## Verify
After fixing, add the diagnostic print statements back temporarily and confirm the actual callback order matches what the fix assumes, then remove the prints. Also run the test class after adding an unrelated new field or extension to confirm the fix isn't fragile to declaration order (it should still pass regardless of where the new field is inserted).
