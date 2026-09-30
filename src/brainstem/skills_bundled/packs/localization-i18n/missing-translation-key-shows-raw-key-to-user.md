---
name: missing-translation-key-shows-raw-key-to-user
description: A missing translation for a locale surfaces as a raw untranslated key or a blank string in the live UI instead of falling back gracefully.
triggers: ["user sees translation key instead of text", "raw i18n key showing in production", "blank text where translation should be", "missing_translation showing on screen", "untranslated string leaking to users"]
permissions: ["READ"]
---

## Symptom
A user in a non-default locale sees something clearly broken instead of translated text: a raw internal key like `settings.notifications.email_digest_frequency` rendered verbatim on screen, an empty label/button with no text at all, or (in some frameworks) a bracketed placeholder like `[missing translation]`. It usually affects only newly added strings or a specific locale that lags behind the primary one in translation coverage, and often isn't caught in QA because QA is commonly done in the source/default locale where the key always resolves.

## Likely causes
1. **A new string was added to the source locale's resource file but the translation pipeline hasn't yet produced (or hasn't been deployed with) the corresponding entry for other locales**, and the i18n library's default behavior for a missing key is to render the key itself or nothing, rather than falling back to another language.
2. **No fallback locale chain is configured**, so when a key is missing for, say, `fr-CA`, the library doesn't know to fall back to `fr` or to the default/source locale (`en`) -- it just fails to resolve and shows whatever its bare-missing-key default is.
3. **A translation key was renamed or restructured (refactored) in the source locale's file but the rename wasn't propagated to already-translated locale files**, silently orphaning the old key's translations and creating a new key with none -- this is functionally identical to a missing translation but caused by a refactor rather than new content.
4. **The translation resource files are lazy-loaded or code-split per locale/route, and a race condition or bundling gap means the translation bundle for the active locale hasn't finished loading when the component first renders**, producing a transient missing-key flash even though the translation exists and will resolve correctly on a later render.
5. **The build/deploy pipeline for translation updates runs on a different cadence than code deploys**, so a code change ships with a brand-new key before the translation vendor or localization team has had time to translate and merge it back in, creating an inherent window where the key is legitimately not yet translated anywhere but the source locale.

## Diagnose
- Reproduce in the affected locale specifically (not the default/source locale) and inspect the rendered output for the exact missing-key pattern the i18n library produces (raw key, bracketed placeholder, or empty string) -- each library has a distinct, recognizable default so this quickly confirms it's a missing-key issue rather than a different rendering bug.
- Check the locale's resource file directly for the presence/absence of the specific key reported -- if absent, check the git history of that key in the default-locale resource file to see if it's newly added or was recently renamed (a rename shows up as the old key disappearing and a new similarly-named key appearing in the same commit).
- Check the i18n library's configuration for a fallback locale chain (e.g. i18next's `fallbackLng`, or the equivalent in the framework in use) and confirm it's actually set, and set to something that would have covered this case (a regional variant like `fr-CA` needs to fall back to `fr` or `en`, not fail directly to nothing).
- If the issue is intermittent/flashes then resolves, check whether translation bundles are lazy-loaded and whether the component renders before the load promise resolves -- add logging or a network-tab check to see the timing between bundle fetch completion and first render of the affected component.
- Check whether the translation update pipeline (vendor handoff, translation management system sync) runs asynchronously from code deploys, and if so, how large the typical lag is -- this tells you whether the specific instance is an expected transient gap or a persistent pipeline break.

## Fix
Configure an explicit fallback locale chain in the i18n library so a missing key in a specific locale resolves to the next-best available translation (regional variant -> base language -> default/source locale) instead of falling through to the library's raw-key or blank default, and set the library's `missing key` handler to log/report the gap (to error tracking or a localization dashboard) rather than silently displaying broken text -- visibility into missing keys is what lets the localization team prioritize fixing the actual gap, rather than only the fallback masking it from users. Separately, add a build- or CI-time check that fails (or at least warns loudly) when a key exists in the source locale's resource file but is absent from a shipped locale's file, so gaps are caught before deploy rather than reported by users; for the specific case of key renames, require the refactor to update all locale files atomically in the same change rather than only the source file.

## Pitfalls
- Setting the fallback locale to the source/default language (usually English) as the *only* fallback for every locale hides missing-translation gaps well enough that they stop getting reported and fixed -- pairing the fallback with active logging/monitoring of fallback hits is what prevents the gap from becoming permanent by being invisible.
- Suppressing the missing-key symptom by making the library return an empty string instead of the raw key "looks less broken" to a user but is strictly worse for the localization team's ability to detect the problem, and worse for the user, who now sees no information at all instead of at least a readable (if wrong-language) fallback string.
- Fixing the immediate reported key without addressing why the pipeline allowed a key to ship without translations (async translation/deploy cadence, no CI gate) means the next new string added will reproduce the same bug for a different key.

## Verify
Deliberately remove or rename a test key in the default locale's resource file only (leaving other locales untouched), load the app in an affected non-default locale, and confirm it displays the configured fallback (a readable string in the next-best locale, not a raw key or blank), while also confirming the missing-key event was logged/reported somewhere the localization team would see it -- then restore the key and confirm normal resolution returns.
