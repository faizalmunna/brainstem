---
name: hardcoded-date-format-shows-ambiguous-date
description: A hardcoded MM/DD/YYYY date format displays an ambiguous or flipped date to users in locales that expect DD/MM/YYYY or YYYY-MM-DD ordering.
triggers: ["date shows wrong day and month swapped", "03/04/2026 ambiguous date bug", "hardcoded date format wrong for uk users", "MM/DD/YYYY breaking for european locale", "date parsing swaps day and month"]
permissions: ["READ"]
---

## Symptom
A date renders correctly for US-based testers but is reported as wrong -- or silently misread -- by users elsewhere: `03/04/2026` is intended as March 4th but a UK or European user reads it as 3 April, and in cases where the value round-trips through a date picker or is re-parsed, the day and month get transposed entirely (April 3rd becomes March 4th in storage). The bug is often invisible in testing because any date where day and month are both ≤12 "looks plausible" in either ordering, so QA in a single locale doesn't catch it -- it only surfaces for dates like the 13th through 31st of a month, or when a customer in a different region reports a wrong appointment/deadline date.

## Likely causes
1. **The format string is hardcoded** (`MM/DD/YYYY`, a manual `date.getMonth()+1 + "/" + date.getDate()`, or a template literal) instead of using a locale-aware date formatter, so every user sees the same ordering regardless of their actual locale.
2. **A date string is parsed with an assumed format instead of an unambiguous one** -- code does `new Date("03/04/2026")` and relies on the JS engine's (or another language's date library's) implementation-defined parsing of slash-separated dates, which varies by locale/engine and silently produces a different date object than intended, rather than parsing an explicit ISO 8601 string (`2026-03-04`) which has one unambiguous interpretation everywhere.
3. **The date is round-tripped through display formatting and back** -- a UI shows a locale-formatted date, the user or another system re-enters/re-submits that displayed string, and the parser on the receiving end assumes its own default ordering, silently transposing day and month for any input where both are ≤12.
4. **Locale-aware formatting was added for display but the underlying storage/API layer still uses or accepts ambiguous slash-delimited strings** instead of ISO 8601 or Unix timestamps, so the ambiguity is just moved rather than eliminated, and any client with a different locale default reintroduces the bug.

## Diagnose
- Search the codebase for hardcoded format strings (`MM/DD/YYYY`, `DD/MM/YYYY`, manual string concatenation of `getMonth()`/`getDate()`) and for `new Date(string)` calls parsing a slash- or dash-delimited string that isn't already ISO 8601.
- Reproduce with a date where day and month are unambiguous under one ordering but not the other -- e.g. render/parse the 13th of any month (`13/03/2026`) under both `en-US` and `en-GB` locale settings and confirm whether the app produces two different actual dates or a parse error in one of them.
- Check what format the API/database actually stores and transmits dates in -- if it's anything other than ISO 8601 (`YYYY-MM-DD`) or a numeric timestamp/epoch, that's a second ambiguity point independent of the display layer.
- Audit every place a date crosses a serialization boundary (form submission, API request/response, CSV export/import, log line) for whether it uses an explicit, unambiguous format at that boundary, since display-layer fixes don't help if the wire format is still ambiguous.

## Fix
Separate "how a date is stored/transmitted" from "how a date is displayed," and make the first one always unambiguous: store and transmit dates as ISO 8601 strings or numeric timestamps everywhere internally (API payloads, database columns, logs, URLs), and only convert to a locale-specific display string at the final render step using a locale-aware formatter (`Intl.DateTimeFormat(locale, options)` in JS, or the equivalent in the platform's standard library) that derives the day/month/year ordering from the user's actual locale rather than a hardcoded template. When parsing user input, use a date-picker component that returns a structured date value (not a raw string) or an explicit format matching what was displayed, rather than re-parsing a locale-formatted display string with an assumed format.

## Pitfalls
- Fixing only the display layer (switching to `Intl.DateTimeFormat`) while leaving API payloads or CSV exports as ambiguous slash-delimited strings just relocates the bug to any integration or downstream consumer that assumes a different default ordering.
- Assuming the browser's or OS's locale setting reliably reflects the user's date-format preference -- some users run their OS in one locale but prefer a different date convention, so where the product supports it, an explicit user-facing format preference (independent of translation locale) avoids incorrect assumptions.
- "Fixing" ambiguous parsing by special-casing the format based on request origin (e.g. IP-inferred country) rather than an explicit locale/format signal reintroduces the same ambiguity for VPN users, travelers, or shared/proxied networks.

## Verify
Pick a test date whose day is 13-31 (so it's invalid or different under the other ordering), and confirm the value displays correctly under at least two different locale settings (e.g. `en-US` and `en-GB` or `de-DE`) without changing the underlying stored value -- then trace that same date through a full round trip (display, user re-entry or export, re-import, re-display) and confirm the stored/transmitted value never changes across the trip, only its rendered representation does.
