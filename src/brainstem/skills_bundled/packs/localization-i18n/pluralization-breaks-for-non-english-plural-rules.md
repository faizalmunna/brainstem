---
name: pluralization-breaks-for-non-english-plural-rules
description: Pluralized UI text is grammatically wrong in Russian, Arabic, or Polish because the code only handles English's singular/plural split.
triggers: ["plural translation looks wrong in russian", "arabic plural forms broken", "count text is wrong for polish locale", "why does 5 items show the wrong word", "ngettext not handling all plural cases"]
permissions: ["READ"]
---

## Symptom
An English string like `"{count} item(s)"` or a hand-rolled `count === 1 ? "item" : "items"` ternary gets translated and shipped. For English, French, German, or Spanish users it looks fine. For Russian, Polish, Arabic, or other locales, native speakers report that the count text reads as ungrammatical or nonsensical -- e.g. a Russian string that's correct for "1, 21, 31 files" but wrong for "2-4 files" and wrong again for "5-20 files", or an Arabic string that never accounts for the dual form (exactly 2).

## Likely causes
1. **The pluralization logic is a hardcoded binary check** (`count === 1 ? singular : plural`) baked into application code or a template, which structurally cannot represent languages with more than two plural categories -- Russian has 4 (one/few/many/other), Arabic has 6 (zero/one/two/few/many/other), Polish has 4, and each maps counts to categories by different modulo rules.
2. **The i18n library supports CLDR plural rules but the translation was added as a single flat string** instead of a keyed plural object (e.g. a translator or engineer pasted one string into a slot meant for `one`/`few`/`many`/`other` variants, or the extraction tooling only pulled out two forms because the source English only has two).
3. **The plural category is selected using the source language's rule instead of the target locale's rule** -- code computes "is this singular or plural" once in English semantics and passes a boolean flag downstream, so by the time the target-language string is chosen there's no way to distinguish "few" from "many" even if translations for those categories exist.
4. **Interpolation happens before pluralization**, so the count is stringified and concatenated into a pre-selected singular/plural template rather than being passed to the pluralization function itself, which breaks any locale where the plural category depends on more than the last digit (Arabic's rules depend on the whole number, not just count % 10).

## Diagnose
- Grep the codebase for ternaries or `if (count === 1)` / `count == 1` patterns near user-facing strings -- this is the direct fingerprint of hardcoded binary pluralization.
- Check whether the i18n library in use (ICU MessageFormat, `Intl.PluralRules`, gettext `ngettext`/`Plural-Forms`, Fluent, i18next with `_plural` suffixes) is actually invoked, or whether it's installed but bypassed by a manual conditional elsewhere.
- For a suspect string, run `new Intl.PluralRules('ru-RU').select(count)` (or the target locale) across a representative range of counts (0, 1, 2, 3, 4, 5, 11, 21, 22, 25, 100) and confirm the app's chosen category matches for each -- Russian alone needs distinct handling for 1, 2-4, 5-20, and 21+ patterns.
- Inspect the translation resource file for the affected locale (`.po`, `.json`, `.ftl`) and confirm it has an entry for every plural category CLDR defines for that locale (check `unicode.org/cldr` plural rules or the library's bundled CLDR data), not just `one`/`other`.
- Ask a native speaker or use a locale-aware review to confirm the "few"/"many" category strings are grammatically distinct from "other" -- a translator sometimes fills every slot with the same string as a stopgap, which passes structural checks but is still wrong.

## Fix
Route every countable string through the i18n library's plural API instead of custom conditionals, and treat the plural category as locale-owned data, not application logic: the app supplies a count, the library (using CLDR rules for the active locale) selects which category applies, and translators fill in as many categories as that locale requires -- two for English, four for Russian/Polish, six for Arabic. This means the translation resource format must support keyed plural variants (ICU `{count, plural, one {...} few {...} many {...} other {...}}`, gettext `Plural-Forms` with `ngettext`, or the equivalent), and any code that currently branches on `count === 1` needs to be replaced with a call into that API so the category selection logic lives in one place shared across all locales instead of being reimplemented per-string.

## Pitfalls
- Adding a plural object for a locale but filling unused categories with a copy-pasted string "to make the schema valid" ships something that passes automated checks (all keys present) but is still linguistically wrong -- a native-speaker review step is needed, not just structural validation.
- Assuming "we support i18n plurals" because the library exists is not the same as verifying every user-facing count string actually calls the plural API rather than a leftover ternary from before the library was adopted -- partial migrations are common and easy to miss without a codebase-wide audit.
- Selecting the plural category from the *formatted* (locale-adjusted, e.g. grouped or translated-digit) string instead of the raw numeric count can select the wrong category, since formatting and pluralization must both derive from the same underlying number.

## Verify
For each locale the product ships, iterate a numeric test range (at minimum 0, 1, 2, 3, 4, 5, 10, 11, 20, 21, 22, 25, 100, 101) through the actual rendering path and confirm both that `Intl.PluralRules` (or the library's equivalent) selects the category CLDR defines for that count in that locale, and that the resulting rendered string reads correctly to a native speaker -- automate the category-selection check in a test, and get the grammatical check from a real bilingual reviewer or professional translation QA pass, since no automated tool can confirm grammatical correctness.
