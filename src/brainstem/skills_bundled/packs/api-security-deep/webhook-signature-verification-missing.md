---
name: webhook-signature-verification-missing
description: A webhook receiver endpoint processes incoming callbacks without verifying the sender's signature, letting anyone forge requests that trigger real application logic.
triggers: ["webhook endpoint accepts unsigned requests", "anyone can call our webhook and trigger an action", "forged webhook payload processed", "verify webhook signature implementation"]
permissions: ["READ"]
---

## Symptom
An endpoint built to receive callbacks from an external system (a payment processor, a CI provider, a SaaS integration) accepts and fully processes any POST to that URL, regardless of who sent it. Anyone who discovers or guesses the endpoint URL can send a crafted payload -- e.g. a fake "payment succeeded" or "subscription upgraded" event -- and the application acts on it as if it came from the real provider, because the handler trusts the payload's content rather than verifying its origin.

## Likely causes
1. **The webhook handler was built and tested against the provider's payload shape but never implemented the provider's signature verification step**, which is usually optional-looking in the provider's docs (a separate section, sometimes skipped during initial integration because "it works" without it).
2. **The verification secret is mismatched or missing in one environment** -- signature checking exists in code but the signing secret was never configured for a given deployment (staging often gets this wrong first, but the same misconfiguration pattern reaches production), and the code fails open (skips verification) rather than fails closed when the secret is absent.
3. **The endpoint checks a weaker signal instead of a cryptographic signature** -- e.g. it checks that the request has a specific header present, a User-Agent string, or that it comes from an IP range that's outdated or spoofable, none of which prevent a forged payload from a determined attacker.
4. **Signature verification exists but is done incorrectly** -- comparing signatures with a non-constant-time string comparison (timing attack surface), verifying against the wrong payload encoding (parsed/re-serialized JSON instead of the exact raw bytes the provider signed), or not checking a timestamp/nonce, which allows replay of a previously valid, captured payload.

## Diagnose
- Read the webhook provider's documentation for their specific signature scheme (e.g. Stripe's `Stripe-Signature` header with HMAC-SHA256 over timestamp+payload, GitHub's `X-Hub-Signature-256`) and confirm the handler implements exactly that scheme, not a simplified approximation.
- Send a crafted POST directly to the webhook endpoint (via curl, outside the provider) with a plausible payload and no valid signature header, in a test/staging environment, and confirm the endpoint rejects it (4xx) rather than processing it.
- Check whether the code path that verifies the signature can be bypassed when the signing secret environment variable is unset -- test by temporarily unsetting it in a non-production environment and confirming the handler fails closed (rejects all requests) rather than open.
- Grep the signature comparison code for `==` or `.equals()` on the computed vs. received signature instead of a constant-time comparison function (`hmac.compare_digest`, `crypto.timingSafeEqual`), and check whether the verified payload is the exact raw request body versus a re-parsed/re-serialized version (which can differ from what was actually signed).

## Fix
Verify every inbound webhook cryptographically before processing it, and fail closed:
- Implement the provider's documented HMAC signature verification using the raw, unparsed request body (capture bytes before any JSON parsing/middleware transformation touches them), and use a constant-time comparison function for the signature check.
- Store the signing secret per-provider-integration in your secrets manager, and make the application refuse to start (or refuse all webhook traffic) if the secret is missing, rather than silently skipping verification -- fail closed, not open.
- Verify the payload's timestamp is recent (reject anything older than a few minutes) to prevent replay of a captured, previously-valid payload, and where the provider supports it, track processed event IDs to reject exact duplicates (idempotency also protects against double-processing legitimate retries).
- Treat the webhook payload itself as untrusted input even after signature verification passes -- validate its schema and apply the same authorization logic you'd apply to any external input (e.g. confirm the referenced order/customer ID actually belongs to the account the webhook claims).

## Pitfalls
Don't substitute IP allowlisting for signature verification as the primary control -- provider IP ranges change, are documented as unstable by most providers, and don't protect against an attacker who compromises a system that legitimately has that IP. IP allowlisting is a reasonable defense-in-depth addition, never a replacement for cryptographic verification.

## Verify
In a staging environment, capture a real webhook payload and signature from the provider, replay it after altering one field in the JSON body without recomputing the signature, and confirm the endpoint rejects it -- then replay the unaltered original after its timestamp window has expired and confirm that's rejected too.
