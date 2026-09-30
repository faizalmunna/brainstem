---
name: concatenated-translation-fragments-produce-wrong-grammar
description: A sentence built by concatenating separately translated word fragments reads grammatically incorrect or nonsensical in languages with different word order than English.
triggers: ["translated sentence word order wrong", "concatenated strings broken in german", "sentence built from fragments doesn't make sense translated", "translation reads backwards in another language", "string interpolation breaks grammar in translation"]
permissions: ["READ"]
---

## Symptom
A sentence is assembled at runtime by joining several independently translated pieces -- e.g. `t("you_have") + " " + count + " " + t("new_messages") + " " + t("from") + " " + userName` -- and it reads fine in English ("You have 3 new messages from Alex") but comes out grammatically broken, word-order-scrambled, or outright nonsensical once each fragment is translated into a language with different syntax (German verb-final clauses, Japanese SOV order, languages requiring gendered or case-inflected agreement between the fragments). Translators flag that they "can't fix" the sentence because they only see isolated fragments like `"you_have"` or `"from"` with no context for how they'll be joined, and any correct translation for one language breaks the concatenation order assumed by the code.

## Likely causes
1. **The sentence is built by string concatenation of independently-keyed translation fragments**, so the code -- not the translation -- fixes the word order permanently in the source language's order, leaving translators no way to reorder fragments even if their language requires it.
2. **Fragments are translated in isolation without sentence-level context**, so a translator sees `"from"` as a standalone string and can't know it needs a different preposition, case ending, or position depending on what precedes/follows it in the final assembled sentence.
3. **Variable interpolation is treated as plain string substitution instead of using a message-formatting system**, so values like counts or names can't trigger grammatical agreement (gender, case, pluralization) in the surrounding fragments the way real sentence-templating systems (ICU MessageFormat, gettext with full-sentence msgids) support.
4. **A translation key is reused across multiple different sentence contexts** (e.g. `"from"` used both as "from [person]" and "from [date]") assuming the same target-language word works in both, which is often false and forces translators to either mistranslate one context or the key gets duplicated inconsistently across the codebase.

## Diagnose
- Grep for string concatenation or template literals combining multiple `t()`/translation-function calls into one user-facing sentence (`t("a") + " " + t("b")`, or `` `${t("a")} ${value} ${t("b")}` ``) -- this is the direct fingerprint.
- For any flagged case, check the translation resource file for the fragment keys involved and confirm whether they're generic, context-free strings ("from", "and", "the") reused across multiple sentences -- a reused, ultra-short key is a strong signal of fragment-based assembly.
- Get a native-speaker or professional-translator review of the assembled (not fragment-level) output for a target language with substantially different word order (German, Japanese, Arabic, or a language with grammatical gender/case) -- structural bugs like this are invisible to automated string-completeness checks and only surface as "this doesn't read right" from a human reader.
- Check whether the i18n framework in use supports full-sentence message templates with named placeholders (ICU MessageFormat's `{name}` interpolation, gettext's whole-sentence msgids with `%(name)s`) and whether it's actually being used for this string or bypassed in favor of concatenation.

## Fix
Replace fragment concatenation with a single, full-sentence translation key per distinct message, using named placeholders for the variable parts: `t("new_messages_notification", { count, userName })` mapping to one template string per locale, e.g. `"You have {count} new messages from {userName}"` in English and a from-scratch, grammatically correct equivalent in each other locale -- giving translators the entire sentence in context, with the freedom to reorder placeholders, add case/gender agreement, or restructure the clause however their language requires, since the template (not application code) controls word order per locale. For messages with count- or gender-dependent grammatical variation beyond simple pluralization, use the i18n library's `select`/`plural` formatting constructs (ICU MessageFormat) so a single key can branch into multiple grammatically distinct forms per locale rather than requiring separate concatenated fragments.

## Pitfalls
- Switching to placeholder interpolation but keeping the sentence split into two or three keys "for reuse" (e.g. still separating a greeting key from a body key) reintroduces the exact same word-order rigidity at a coarser granularity -- the fix requires one key per distinct complete sentence, not fewer, smaller concatenations.
- Adding named placeholders without giving translators surrounding context (a comment or a rendered preview showing what `{userName}` and `{count}` will typically contain) still produces awkward translations, since a translator needs to know a placeholder is a proper noun, a count, or a date to phrase the sentence correctly.
- Assuming a template with placeholders is automatically correct for languages requiring grammatical agreement (e.g. a name's gender affecting a following verb or adjective) -- some languages need the translation system to support gender/case selectors on top of plain interpolation, not just placeholder substitution.

## Verify
Have a native speaker (or professional localization QA) read the fully assembled, rendered sentence -- not the individual translation keys -- for each shipped locale, specifically checking a locale with substantially different word order (German, Japanese, or Arabic) and confirming the sentence is grammatically natural, not just "technically contains all the right words." Additionally, confirm structurally that no user-facing sentence in the codebase is still built via multi-fragment string concatenation by searching for the anti-pattern directly.
