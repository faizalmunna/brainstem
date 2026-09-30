---
name: assertj-vs-junit-assertion-message-mismatch
description: A failing assertion prints a confusing or truncated message that doesn't clearly show the actual versus expected values, slowing down debugging.
triggers: ["assertion failure message unclear", "assertEquals expected actual reversed", "AssertionFailedError doesn't show diff", "toString not helpful in test failure output"]
permissions: ["READ"]
---

## Symptom
A test fails and the console shows something unhelpful like `org.opentest4j.AssertionFailedError: expected: <Order@4a5f2c1> but was: <Order@7b3e910>` -- object hash-based identity strings instead of readable field values -- or the expected/actual arguments are visibly swapped (`assertEquals(actualValue, expectedValue)` instead of `assertEquals(expectedValue, actualValue)`), making the failure message actively misleading about which value came from where.

## Likely causes
1. **The class being compared doesn't override `toString()`**, so JUnit's default failure message falls back to `ClassName@hashcode`, giving no readable information about which fields actually differ.
2. **`assertEquals(actual, expected)` arguments are reversed** -- JUnit 5's convention is `assertEquals(expected, actual)`, and getting this backwards doesn't cause a wrong pass/fail, but it does produce a failure message with "expected" and "actual" swapped, which is actively confusing during triage.
3. **Comparing collections or complex objects field-by-field with plain `assertEquals` gives an all-or-nothing failure** with no indication of *which* field or *which* element differs, forcing manual inspection instead of reading the failure message.
4. **Mixing assertion libraries inconsistently across the codebase** (some tests use JUnit's `Assertions.assertEquals`, others use AssertJ's `assertThat(...).isEqualTo(...)`, others use Hamcrest) means engineers can't build a consistent mental model of what a given failure message will look like, and some of those libraries produce much richer diffs than others for the same kind of comparison.

## Diagnose
1. Read the exact failure message text: does it show field values, or just `ClassName@hashcode`? The latter means `toString()` is missing or unhelpful on the compared type.
2. Check the assertion call's argument order against the library's documented convention -- for JUnit 5 `assertEquals(expected, actual, [message])`; a reversed call is a quick visual check once you know which side should be which.
3. For collection/object comparisons, check whether the assertion is a single `assertEquals(expectedList, actualList)` (opaque failure) versus an AssertJ `assertThat(actualList).containsExactlyElementsOf(expectedList)` (element-by-element diff in the failure message).
4. Grep the test module for which assertion libraries are in use (`import org.assertj`, `import static org.junit.jupiter.api.Assertions`, `import org.hamcrest`) to see whether the project has a de facto standard being ignored in this particular test.

## Fix
Prefer AssertJ's fluent assertions for anything beyond a trivial primitive comparison -- its failure messages are built specifically to show a readable diff, including field-by-field breakdowns for objects and element-level diffs for collections:

```java
// JUnit plain equality -- opaque on failure without a good toString()
assertEquals(expectedOrder, actualOrder);

// AssertJ -- on failure, prints which specific fields differ
assertThat(actualOrder)
    .usingRecursiveComparison()
    .isEqualTo(expectedOrder);

// AssertJ collection comparison -- shows exactly which elements are missing/extra/out of order
assertThat(actualItems).containsExactlyElementsOf(expectedItems);
```

`usingRecursiveComparison()` is the key pattern for object comparisons: it walks the object graph field by field and reports precisely which field(s) mismatched and with what values, rather than relying on `equals()`/`toString()` being implemented well (or at all) on the domain class.

## Pitfalls
`usingRecursiveComparison()` compares *all* fields by default, including ones like generated IDs, timestamps, or audit fields that legitimately differ between expected and actual test fixtures -- leading to false failures on fields the test doesn't actually care about. Use `.ignoringFields("id", "createdAt")` or `.comparingOnlyFields(...)` deliberately rather than abandoning recursive comparison the first time it flags an irrelevant field.

## Verify
Deliberately break one field in the test fixture (e.g. change an expected string) and re-run the test -- confirm the failure message names the specific field and shows both the expected and actual value for it, rather than just reporting "not equal" with opaque object references.
