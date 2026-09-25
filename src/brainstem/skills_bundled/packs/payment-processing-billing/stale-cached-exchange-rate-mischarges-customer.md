---
name: stale-cached-exchange-rate-mischarges-customer
description: A customer paying in a non-default currency is charged based on a cached exchange rate that no longer matches the current rate, over- or under-billing relative to the intended price.
triggers: ["wrong amount charged in foreign currency", "exchange rate stale", "multi-currency price mismatch", "customer charged wrong amount after fx move"]
permissions: ["READ"]
---

## Symptom
A product priced in a base currency (e.g. USD) is sold to a customer in
another currency (e.g. EUR, GBP, JPY) via a converted/localized price, and
the amount actually charged doesn't match what the current market
exchange rate would produce -- sometimes noticed by finance reconciling
converted revenue against expected base-currency totals, sometimes by a
customer comparing the price they see today against what a friend was
charged, and it points back to a currency conversion rate that was cached
or fetched at some point in the past and reused past its useful window.

## Likely causes
1. **A converted price is computed once and cached for a fixed TTL that's
   too long relative to how much the underlying rate moves**, so a
   customer checking out hours or days after the price was cached pays a
   rate that no longer reflects the market, and during volatile periods
   this gap can be economically significant.
2. **The price is cached indefinitely with no invalidation trigger at
   all** -- computed once at product-catalog-sync time and never
   refreshed until someone notices and manually forces a recompute.
3. **The rate used at checkout differs from the rate used at
   authorization/capture time for a delayed-capture flow** (e.g. an order
   is authorized when placed but captured on shipment days later), and the
   system re-fetches a fresh rate at capture rather than locking in the
   rate that was quoted to the customer at checkout, so the amount
   actually captured differs from the amount the customer agreed to.
4. **Multiple parts of the system fetch/cache exchange rates
   independently** (e.g. the pricing display and the actual charge
   computation use separate rate sources or separate cache instances with
   different refresh schedules), so what the customer is shown and what
   they're actually charged can disagree even without either being
   individually "stale" by an obvious amount.

## Diagnose
- Find the exact rate used for a specific disputed transaction (log it at
  charge time if not already logged) and compare it against the actual
  market rate at that timestamp from an independent source -- a
  significant gap confirms staleness; a rate that matches an *older*
  timestamp's market rate confirms exactly how stale the cache was.
- Check the cache/storage layer for the exchange rate: what's the TTL, and
  is there any invalidation trigger, or does it simply expire and get
  lazily refreshed on next access (which can itself serve one more stale
  read after expiry under concurrent access)?
- For delayed-capture flows, check whether the rate is stored on the order
  at authorization time or re-fetched at capture time -- grep the capture
  code path for whether it reads a stored `exchange_rate` field on the
  order/invoice or calls the rate service fresh.
- Check whether pricing-display code and charge-computation code call the
  same rate-fetching function/service, or two separately maintained ones.

## Fix
Lock in the exchange rate at the moment the customer commits to a price
(checkout/authorization) by storing the rate value itself on the
order/invoice record, and use that stored rate for any later capture or
adjustment on that same order -- never re-fetch a "current" rate for an
operation that's supposed to honor a price the customer already agreed
to. For rates used in ongoing display/quoting (before commitment), choose
a refresh interval deliberately based on how much currency pairs
realistically move and how much mispricing risk is acceptable (minutes to
low hours for volatile pairs, not days), and make the display and the
actual charge path read from the same single rate source/cache so they
can't silently disagree. Make rate cache invalidation explicit (event- or
TTL-driven with monitoring on cache age) rather than purely lazy, so a
stale rate doesn't silently persist just because traffic on that currency
pair happened to be low.

## Pitfalls
- Locking the rate at checkout but then still calling a "fresh" rate
  lookup somewhere downstream (webhooks, retries, reconciliation reports)
  that overwrites or second-guesses the locked-in value -- audit every
  place the order's currency amount is touched, not just the primary
  charge path.
- Shortening the TTL aggressively without also handling the rate
  provider's own rate limits or outages -- a rate-fetch failure shouldn't
  silently fall back to an even-more-stale cached value without at least
  logging/alerting that the fallback happened.
- Rounding the converted amount inconsistently between the quoted price
  and the charged price (a variant of the general money-rounding pitfall)
  even when the rate itself is correctly locked -- verify the same
  rounding rule is applied at both points.

## Verify
Force the cached exchange rate for a test currency pair to a known,
deliberately stale value, initiate a checkout, and confirm the amount
charged matches the locked-in rate captured at checkout (not a rate
refreshed later); separately, advance the mocked "current time" past the
cache TTL without any explicit invalidation event and confirm the system
does not serve the expired value past its intended freshness window.
