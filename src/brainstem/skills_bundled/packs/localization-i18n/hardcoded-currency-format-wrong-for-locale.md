---
name: hardcoded-currency-format-wrong-for-locale
description: Hardcoded currency formatting shows the wrong symbol placement or decimal separator convention for users outside the original target locale.
triggers: ["price shows wrong decimal separator", "currency symbol in wrong place for locale", "1.234,56 vs 1,234.56 bug", "hardcoded dollar sign for european users", "price formatting wrong for german locale"]
permissions: ["READ"]
---

## Symptom
Prices display incorrectly for users outside the locale the code was originally written for: a price meant to read "1,234.56" (US convention: comma thousands separator, period decimal) instead shows as "1.234,56" territory expectations reversed, or vice versa -- a German or French user sees "$19.99" formatted with a period decimal when their convention expects a comma, or a price built with string concatenation shows the currency symbol on the wrong side of the number ("19.99 €" vs "€19.99"). In the worst case, the ambiguity causes a real misunderstanding of magnitude -- a user reads "1.234" as "1.234" (a bit over one) when it was meant as "1,234" (one thousand two hundred thirty-four), because the decimal/thousands separator convention is inverted from what they expect.

## Likely causes
1. **The currency string is built manually** (`"$" + amount.toFixed(2)`, or a template literal hardcoding a `$` prefix and period decimal) instead of using a locale-aware currency formatter, so every user sees the same symbol, placement, and separators regardless of their locale.
2. **The decimal/thousands separator is hardcoded as period-and-comma** (the US/UK convention) without accounting for locales that use the reverse convention (comma decimal, period or space thousands separator -- common across most of continental Europe and Latin America).
3. **Currency symbol and currency code are conflated**, or the symbol is hardcoded, so a multi-currency product displays every price with the same symbol (e.g. always `$`) regardless of the actual transaction currency, or displays a correct amount in the wrong currency's conventional symbol position for that locale.
4. **Formatting was localized for display but rounding/precision assumptions weren't** -- some currencies have zero decimal places (Japanese yen, Korean won) or three (Bahraini dinar), and a formatter or backend calculation hardcoded to two decimal places produces incorrect-looking amounts (`¥500.00` instead of `¥500`) or, worse, incorrect calculated totals if rounding logic assumes two decimal places universally.

## Diagnose
- Grep for hardcoded currency symbols (`$`, `€`, `£`) or manual string-building of prices (`.toFixed(2)` concatenated with a symbol) rather than a call into a locale-aware formatting API.
- Render a representative price (e.g. 1234.5) through `Intl.NumberFormat(locale, { style: 'currency', currency: code })` (or the platform equivalent) for several locale/currency pairs (`en-US`/USD, `de-DE`/EUR, `fr-FR`/EUR, `ja-JP`/JPY) and diff the output -- confirm separator convention, symbol placement, and decimal-digit count all vary correctly per locale/currency rather than being fixed.
- Check whether currency amounts are stored and calculated as integers (minor units, e.g. cents) or floating-point decimals -- and separately, whether the number of minor units per major unit is hardcoded to 100 (two decimals) anywhere, since currencies like JPY have zero and others have three.
- Confirm the locale and the currency are tracked as two independent pieces of data (a French user might be paying in USD, or a US user might be viewing prices in EUR) rather than one being inferred from the other.

## Fix
Format every user-facing currency amount through a locale-aware formatter that takes both the target locale (for separator/symbol-placement conventions) and the actual transaction currency code (ISO 4217, e.g. `USD`, `EUR`, `JPY`) as independent inputs -- `Intl.NumberFormat(locale, { style: 'currency', currency: currencyCode })` in JavaScript, or the equivalent in the platform's standard library -- rather than hardcoding a symbol or separator convention anywhere in application code. Store monetary amounts internally as integers in the currency's minor unit (cents, or the equivalent smallest unit, using the currency's actual minor-unit count rather than assuming two decimal places) to avoid floating-point rounding errors, and only convert to a formatted major-unit display string at render time.

## Pitfalls
- Localizing the display format but leaving backend arithmetic (totals, discounts, tax calculations) in floating-point major units accumulates rounding errors regardless of how well the final number is formatted for display -- the fix must include integer minor-unit math, not just a formatting layer swap.
- Assuming the currency can be inferred from the display locale (e.g. "French locale implies EUR") breaks for any user viewing the site in one locale while paying in another currency, which is common for travel, remote purchases, or multi-currency accounts -- locale and currency must be tracked and passed independently.
- Hardcoding "two decimal places" as a formatting default after switching to a locale-aware formatter still produces wrong output for zero-decimal currencies (JPY, KRW) or three-decimal currencies (BHD, KWD) unless the formatter is actually given the currency code and allowed to determine precision itself rather than being overridden with a fixed `minimumFractionDigits`.

## Verify
Format the same numeric amount through the currency formatter for at least three locale/currency combinations that differ in separator convention (e.g. `en-US`, `de-DE`, and a zero-decimal currency like `ja-JP`/JPY) and confirm each renders with the correct decimal/thousands separators, correct symbol placement, and correct number of decimal digits for that specific currency -- then trace a calculated total (e.g. subtotal plus tax) through the backend to confirm it was computed in integer minor units and only formatted to a decimal string at the final display step, with no intermediate floating-point rounding drift.
