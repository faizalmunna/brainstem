---
name: locale-switch-does-not-update-already-rendered-content
description: Changing the app's language setting updates newly loaded screens but leaves already-cached or already-rendered content in the previous language.
triggers: ["language switch doesn't update whole app", "some text stays in old language after switching", "mixed language UI after changing settings", "cached content not translated after locale change", "language toggle only affects new pages"]
permissions: ["READ"]
---

## Symptom
A user changes the app's language preference (in settings, or via a language picker) and most of the UI updates immediately, but some content stubbornly stays in the previous language: a sidebar or header that was rendered before the switch, data fetched and cached earlier (a list of item names, category labels from an API response cached client-side), or content in a part of the app the user hasn't navigated to since switching. The result is a visibly mixed-language UI that looks broken even though the underlying translation data for the new locale is completely correct and complete.

## Likely causes
1. **The locale value is read once at application startup or component mount and stored in memory**, so changing the setting updates the stored preference but doesn't trigger already-mounted components to re-render with the new locale -- only components that mount fresh after the switch pick up the new value.
2. **API responses containing localized content (translated field values from the backend, not just UI chrome strings) are cached client-side keyed only by resource ID, not by locale**, so a cache entry fetched under the old locale is served as a stale hit after the locale changes, even though a fresh request would return correctly localized content.
3. **The locale is propagated via a mechanism that doesn't reliably reach every component** -- e.g. passed as a prop from a root component but a deeply nested or portaled component reads a stale closure-captured value, or a subset of the app reads locale from a different source (a URL parameter) than the rest (a global state store), so the two can disagree after a switch that only updates one of them.
4. **Some content is genuinely static per session by design** (e.g. an already-generated PDF, a previously sent email, a server-rendered page cached at a CDN edge keyed by the locale active at generation time) and isn't expected to retroactively change -- in this case the "bug" is actually a mismatch between user expectation and an inherent limitation of pre-generated content, which needs a different fix (regenerate on demand, or set expectations) than a live-rendering bug.

## Diagnose
- Change the locale and, without refreshing the page, navigate to a screen that was already visited before the switch versus one visited for the first time after the switch -- if only the first-time screen shows the new locale, the bug is in state propagation/reactivity, not translation data.
- Check whether locale is stored in reactive/observable state (that triggers re-renders of subscribed components on change) or in a plain variable/closure read once at mount -- inspect the specific components showing stale content for how they obtain their locale value.
- For stale localized *data* (not just UI chrome), check the client-side cache keys for API responses containing translated fields -- confirm whether locale is part of the cache key, since a cache keyed only by resource ID will serve a previous locale's response as a hit after switching.
- Check for multiple, independent sources of locale truth in the app (a global store, a URL param, a cookie, a per-component prop) and confirm they're synchronized on every locale change -- a switch that updates only one of several sources leaves any component reading from another source stale.

## Fix
Store the active locale in reactive/observable global state that every locale-dependent component subscribes to (a store, context, or the framework's equivalent reactivity mechanism), so changing it triggers a re-render of every mounted consumer rather than only affecting components that mount afterward -- this is a state-management correctness issue as much as an i18n one. Include the active locale as part of the cache key for any client-side cache of API responses containing localized/translated data, so a locale switch correctly invalidates (or bypasses) previously cached responses instead of serving stale-locale data as a cache hit. Where content is legitimately pre-generated per locale (static exports, cached server-rendered pages, sent notifications), make clear to the user which locale that specific artifact reflects, or provide a regenerate action, rather than presenting it as something the live language switch should have affected.

## Pitfalls
- Forcing a full page reload on every locale switch "fixes" stale-component symptoms by brute force but discards in-progress user state (unsaved form input, scroll position, navigation history) -- prefer fixing the underlying reactivity/cache-key issue so a switch can update in place without losing user context.
- Including locale in the cache key for every API response indiscriminately, including genuinely locale-independent data, needlessly duplicates cache entries and increases cache misses -- only data that actually varies by locale (translated fields) needs locale in its cache key.
- Assuming a single global locale store fixes everything without auditing for a second, independent locale source (a stale URL param, a separately-stored cookie) that some code paths still read from -- partial migrations to a single source of truth are a common way this bug persists after an apparent fix.

## Verify
Switch the locale without reloading the page, then check both a previously-visited screen and a fresh navigation for consistent language, and separately verify that any cached API-backed localized content (not just static UI strings) reflects the new locale on the next fetch -- confirm this by inspecting the actual cache keys/entries used before and after the switch, not just the visually rendered result.
