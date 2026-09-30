---
name: mockito-final-class-mock-silently-ignored
description: Mocking a final class or final method compiles and runs but the real implementation executes anyway instead of the stubbed behavior.
triggers: ["mock final class not working", "Mockito stub ignored real method runs", "UnnecessaryStubbingException on final class mock", "MockMaker inline not enabled"]
permissions: ["READ"]
---

## Symptom
A test does `SomeFinalClass mock = mock(SomeFinalClass.class); when(mock.doThing()).thenReturn("stubbed");`, the test compiles fine and doesn't throw at mock-creation time, but when the code under test calls `doThing()`, the *real* method body runs instead of returning `"stubbed"`. Sometimes this instead manifests as `UnnecessaryStubbingException` at the end of the test, because Mockito recorded the stub but the real class's bytecode was never intercepted.

## Likely causes
1. **The class or the specific method is `final`, and the project is using Mockito's default subclass-based mock maker**, which creates mocks by subclassing the target class at runtime -- something that's fundamentally impossible for `final` classes and no-ops for `final` methods. Older Mockito versions (before the inline mock maker became default in Mockito 5) required opting in explicitly.
2. **A common real-world trap: mocking JDK/third-party final classes** like `java.time.LocalDateTime` (many of its static factory results are effectively final types) or common builder-pattern classes from libraries marked `final` for immutability -- these fail the same way but are less obvious because the test author didn't write the class themselves.
3. **The `mockito-inline` artifact (or Mockito 5's default inline maker) isn't on the test classpath**, or the project pinned an older `mockito-core` version without adding `mockito-inline`, so `final` support silently isn't active even though newer Mockito documentation assumes it is.
4. **A `MockMaker` config file exists but is misplaced or misspelled** -- the opt-in mechanism for older Mockito is a plain text file at `src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker` containing exactly `mock-maker-inline`; a typo in the path or filename means Mockito falls back to the default maker without any error.

## Diagnose
1. Check whether the class or the specific method under test is declared `final` -- `javap -p SomeFinalClass.class` or just reading the source.
2. Check the Mockito version in `pom.xml`/`build.gradle`. Mockito 5+ defaults to the inline mock maker (final support built in); Mockito 4 and earlier require the separate `mockito-inline` dependency or the `mockito-extensions` config file.
3. If on an older Mockito version, verify the file `src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker` exists with content exactly `mock-maker-inline` (no extra whitespace, correct package path).
4. Add a quick isolated check: call the stubbed method immediately after `when(...).thenReturn(...)` with no code under test involved, and see whether it returns the stub or the real value -- isolates whether the problem is mocking itself vs. how the code under test obtains its instance.

## Fix
For Mockito 5+, final-class/method mocking works out of the box -- the fix is usually just upgrading `mockito-core` and removing manual subclass-mock workarounds:

```xml
<dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-core</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
</dependency>
```

For older Mockito or when pinned to Mockito 4, add `mockito-inline` in place of `mockito-core` (it's a drop-in replacement, not an addition):

```xml
<dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-inline</artifactId>
    <version>4.11.0</version>
    <scope>test</scope>
</dependency>
```

The underlying reasoning: the inline mock maker instruments bytecode directly (via an agent) instead of generating a subclass, so `final` is no longer a barrier. If upgrading isn't possible, the fallback pattern is to introduce a thin non-final wrapper/interface around the final class at the seam where it's used, and mock the wrapper instead -- this avoids fighting the mock framework and also improves the design by making the dependency swappable.

## Pitfalls
Don't reach for `PowerMock` to solve this in a modern codebase -- it's unmaintained relative to current JDK versions and adds a heavyweight custom classloader that frequently breaks with newer Java releases and other test tooling. The inline mock maker (built into modern Mockito) covers the vast majority of what PowerMock used to be needed for.

## Verify
After the fix, run the specific test and add a temporary hard assertion that the stub took effect: `assertEquals("stubbed", codeUnderTest.callThatUsesTheFinalClass());` -- confirming the returned value is the stub, not whatever the real final method would compute, proves interception is actually happening rather than the test coincidentally passing.
