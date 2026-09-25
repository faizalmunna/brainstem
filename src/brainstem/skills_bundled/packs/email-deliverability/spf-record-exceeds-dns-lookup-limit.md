---
name: spf-record-exceeds-dns-lookup-limit
description: SPF authentication fails unpredictably because the domain's SPF record exceeds the 10 DNS lookup limit, causing receiving servers to treat it as a permanent error.
triggers: ["spf too many dns lookups", "spf permerror", "spf record exceeds limit", "spf fails intermittently different providers"]
permissions: ["READ"]
---

## Symptom

SPF authentication fails inconsistently across different sending
sources or third-party services that are all legitimately authorized to
send on behalf of a domain, and the failure doesn't correlate with any
obvious misconfiguration in the visible SPF record content -- the actual
cause is that the SPF record's total chain of DNS lookups (including
nested `include:` mechanisms) exceeds the protocol's 10-lookup limit,
causing a permanent error (`PermError`) that many receiving servers
treat as an SPF failure.

## Likely causes

- **Multiple third-party sending services were added to the SPF record
  over time via `include:` mechanisms**, each of which may itself
  perform additional nested lookups, and the cumulative total silently
  crossed the 10-lookup ceiling without anyone tracking the running
  count.
- **A single `include:` mechanism for a large service (a marketing
  platform, a CRM) itself expands into many nested lookups** that aren't
  visible when just reading the domain's own SPF record, since the limit
  applies to the fully resolved chain, not just the top-level directives.
- **Old, no-longer-used sending service `include:` entries were never
  removed** when that service was discontinued, needlessly consuming
  lookup budget that could have been reclaimed.
- **The specific behavior on exceeding the limit is inconsistent across
  receiving mail providers** -- some fail closed (treat as SPF fail),
  others have more lenient interpretations, which makes the symptom look
  like it "depends on the recipient" rather than being a single root
  cause.

## Diagnose

1. Use an SPF record validation/lookup-counting tool to resolve the full
   SPF chain (including all nested `include:` mechanisms) and get the
   actual total DNS lookup count.
2. Identify which specific `include:` entries are the largest
   contributors to the lookup count, distinguishing actively-used
   services from stale ones.
3. Check delivery logs/authentication headers from multiple receiving
   providers to confirm the pattern of failures correlates with SPF
   `PermError` rather than a different authentication issue.
4. Confirm which sending services are currently still actually in use
   versus historical entries that could be removed.

## Fix

Remove `include:` entries for sending services no longer in active use,
reclaiming lookup budget. For services that must remain, consider SPF
flattening (resolving the nested includes to their underlying IP ranges
and listing them directly, avoiding further nested lookups) where the
underlying IPs are stable enough to make this maintainable, understanding
this trades lookup-count savings for a maintenance burden of keeping the
flattened IPs in sync if the provider changes their infrastructure.
Consolidate where possible by using a single well-maintained SPF
flattening/management service if the number of legitimate senders is
large and growing.

## Pitfalls

Don't flatten SPF records without a process to keep the flattened IPs
in sync with the underlying service's actual infrastructure -- a
sending service that rotates or expands its IP ranges will silently
break authentication for a flattened, unmaintained record, trading one
class of failure for another.

## Verify

Re-run the full SPF chain resolution and confirm the total lookup count
is now under the limit with margin for future additions. Send test
emails through every currently-authorized sending service and confirm
SPF passes (not just the primary sending path) across multiple receiving
providers.
