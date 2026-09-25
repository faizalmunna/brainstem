---
name: floating-point-money-rounding-drift
description: Reported balances, invoice totals, or tax amounts drift a few cents away from the sum of their line items after many transactions because money is stored or computed as binary floats.
triggers: ["invoice total off by a cent", "balance doesn't match sum of transactions", "floating point money bug", "tax calculation rounding error", "sums don't reconcile after many charges"]
permissions: ["READ"]
---

## Symptom
A running balance, invoice grand total, or aggregated report doesn't
exactly equal the sum of its individual line items when recomputed --
usually by a tiny amount (fractions of a cent to a few cents) that grows
more noticeable the more transactions accumulate, and finance/accounting
reconciliation flags it as "doesn't tie out" even though no single
transaction looks obviously wrong in isolation.

## Likely causes
1. **Money amounts are stored or computed as IEEE 754 binary floats**
   (`float`/`double` in most languages), and many decimal fractions
   (0.1, 0.2, 0.29, etc.) have no exact binary representation, so
   arithmetic on them (especially repeated addition, or multiplication
   followed by division as in tax/discount/proration math) accumulates
   small representation errors.
2. **Money is correctly stored as integer cents in the database, but
   converted to float at some point in the pipeline** -- a serialization
   layer, an analytics export, a third-party SDK, or a spreadsheet/CSV
   export -- reintroducing the error downstream even though the source of
   truth is fine.
3. **Percentage-based calculations (tax, discounts, fees) round each line
   independently and then sum, rather than summing first and rounding
   once**, so the sum-of-rounded-parts doesn't equal the rounded-whole
   even without any float involved -- a real rounding-policy bug, not
   floating point per se, but presenting with the identical symptom.
4. **Mixing currencies with different minor-unit conventions** (USD has 2
   decimal places, JPY has 0, some currencies have 3) using a single
   hardcoded "divide by 100" assumption, producing amounts off by orders
   of magnitude for zero-decimal or three-decimal currencies specifically.

## Diagnose
- Grep the codebase for the type used to store/pass money: a `float`,
  `double`, `Number` (JS), or untyped numeric column/field is the primary
  suspect; a `DECIMAL`/`NUMERIC` column or integer-cents column with a
  float creeping in somewhere later is the secondary suspect.
- Reproduce with a known adversarial case: sum `0.1 + 0.2` (or the
  equivalent smallest-currency-unit operation) in the exact language/
  runtime used and confirm it doesn't equal `0.3` exactly -- this
  demonstrates the representability issue concretely rather than
  abstractly.
- Trace one specific discrepant invoice/balance end to end: get the exact
  stored value at each stage (database, application layer, API response,
  any export) and find the stage where the value changes unexpectedly --
  this usually pinpoints a specific conversion (e.g. a JSON serialization
  library coercing a decimal string to a JS number).
- Check whether the discrepancy correlates with specific currencies
  (pointing to a minor-unit assumption bug) or is currency-independent and
  scales with transaction volume (pointing to accumulated float error).

## Fix
Store and compute all money values as integers in the currency's smallest
unit (cents for USD, yen for JPY with zero decimal places) or as a
fixed-point/arbitrary-precision decimal type, end to end -- database
column, application model, API payload, and any downstream export --
never converting to a binary float at any stage in the pipeline that does
arithmetic. Look up each currency's actual minor-unit exponent from a
canonical source (e.g. ISO 4217) rather than hardcoding "divide by 100"
everywhere, since zero-decimal and three-decimal currencies are common
enough in multi-currency systems to hit in practice. For tax/discount/fee
math specifically, decide explicitly whether rounding happens per line
item or once on the aggregate, apply that consistently, and reconcile any
per-line rounding remainder into a single designated line (many invoicing
systems add a "rounding adjustment" line for exactly this reason) rather
than letting it silently vanish or double-count.

## Pitfalls
- "Fixing" this by rounding the float to 2 decimal places for display
  only, while still doing the underlying arithmetic in float -- this hides
  the symptom in the UI while the stored/aggregated values are still
  wrong, and the error resurfaces the moment two "already rounded for
  display" values are added together upstream of the display layer.
- Converting to decimal/integer only at the topmost application layer
  while leaving lower layers (serializers, ORMs, analytics pipelines) on
  float -- this just moves the reintroduction point rather than fixing
  it, and those layers need the same audit as the primary code path.
- Switching to a decimal type but still dividing by 100 for every
  currency regardless of its actual minor-unit count -- this fixes the
  binary-representation problem while leaving the zero-decimal-currency
  problem completely intact.

## Verify
Pick a real invoice or account with many (dozens+) of transactions, sum
the stored per-transaction amounts independently (e.g. in a one-off script
using the same integer/decimal type as production) and assert the result
equals the stored aggregate/balance to the exact minor unit -- then repeat
the check for at least one zero-decimal currency (e.g. JPY) to confirm the
minor-unit handling is also correct, not just the float-vs-decimal part.
