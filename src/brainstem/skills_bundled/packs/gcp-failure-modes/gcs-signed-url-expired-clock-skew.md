---
name: gcs-signed-url-expired-clock-skew
description: Google Cloud Storage signed URLs fail with an expiration or signature error even though they were generated with what should be a sufficient validity window.
triggers: ["gcs signed url expired immediately", "signed url invalid signature gcs", "cloud storage presigned url clock skew", "signed url rejected too early"]
permissions: ["READ"]
---

## Symptom

A signed URL generated for temporary access to a Google Cloud Storage
object is rejected as expired or invalid shortly after being generated,
well before the intended expiration window has actually elapsed by wall-
clock time as understood by the client or server generating it.

## Likely causes

- **Clock skew between the server generating the signed URL and Google's
  validation servers** -- if the generating server's clock is
  meaningfully ahead of or behind actual time, the signed timestamp
  embedded in the URL can appear already expired (or not yet valid) from
  Google's perspective.
- **The signed URL's expiration was calculated using a short validity
  window relative to any processing/network delay between generation and
  actual use** -- if the URL isn't used immediately (queued, emailed,
  processed asynchronously), a short window that seemed sufficient at
  generation time can elapse before the client ever uses it.
- **A signing key (particularly for V4 signing, which is time-sensitive
  in its canonical request construction) was generated with an incorrect
  timestamp format or timezone handling**, producing a technically
  malformed signature that manifests as a rejection resembling
  expiration.
- **The URL is being reused after its legitimate single intended use
  window**, and what looks like "immediate" expiration is actually
  correct behavior for a URL that was generated much earlier than
  assumed (e.g. cached and reused past its real expiration).

## Diagnose

1. Compare the exact expiration timestamp embedded in the signed URL
   (decodable from the URL's query parameters) against the actual current
   time when the URL was used, to confirm whether it's genuinely expired
   by the numbers or rejected despite still being within its window.
2. Check the generating server's system clock against a reliable time
   source (NTP sync status) to rule out or confirm clock skew as the
   cause.
3. Trace the actual elapsed time between URL generation and use in the
   real failing scenario (including any queuing, email delivery, or
   asynchronous processing delay) to see if it plausibly exceeds the
   configured validity window.
4. Verify the signing implementation's timestamp/timezone handling
   against Google's documented V4 signing requirements, especially if a
   custom signing implementation is used rather than an official client
   library.

## Fix

Ensure the server generating signed URLs has accurate, NTP-synchronized
time. Set the signed URL's validity window generously enough to account
for realistic delay between generation and actual use in the specific
workflow (not just the expected immediate case), especially for
asynchronous or queued delivery paths. Use official Google Cloud client
libraries for URL signing rather than a hand-rolled implementation,
since they correctly handle the V4 signing timestamp/timezone details
that are easy to get subtly wrong manually.

## Pitfalls

Don't set an extremely long validity window as a blanket fix to avoid
ever hitting this issue -- a signed URL's validity window is also a
security boundary (anyone with the URL can access the object until
expiration), so balance operational convenience against the security
cost of a longer-lived credential-equivalent URL.

## Verify

Generate a signed URL with the corrected validity window and confirm it
works both immediately and after a delay representative of the real
workflow's actual processing time. If clock skew was the root cause,
confirm NTP sync is active and accurate on the generating server going
forward, not just corrected once.
