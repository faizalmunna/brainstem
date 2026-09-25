---
name: shared-api-key-cannot-be-individually-revoked
description: A single API key is shared across many users or services, so revoking it after a leak forces an outage for every legitimate caller at once.
triggers: ["API key leaked but can't revoke without breaking everyone", "rotating API key breaks all integrations at once", "one compromised key affects every customer", "no way to revoke API access for one user"]
permissions: ["READ"]
---

## Symptom
An API key or secret is discovered in a leaked repo, log file, or client-side bundle. The team wants to revoke it immediately, but doing so is known to break every integration, customer, or internal service that happens to use that same key -- because the key was never issued per-caller, only per-application or per-environment. The team either delays revocation (leaving the compromised key live) or revokes it and causes a multi-tenant outage.

## Likely causes
1. **Keys are provisioned per-application/per-environment rather than per-caller or per-tenant** (e.g. one "production API key" baked into a shared config or environment variable used by every customer-facing instance), so there's no way to identify or invalidate just the compromised usage.
2. **No key-to-identity mapping exists at issuance time** -- the system was built to check "is this a valid key" rather than "which principal does this key belong to," so revocation has no scope smaller than "all valid keys of this type."
3. **Client-side embedding of a server-side-scoped key** (e.g. a backend API key hardcoded into a mobile app or frontend bundle) means every install of that app version shares one credential, and revoking it breaks the app for all users until a new release ships.
4. **No key rotation or expiry lifecycle was ever built**, so the key has been live for years, is embedded in more places than anyone tracked, and the blast radius of revocation is unknown because there's no inventory of who's using it.

## Diagnose
- Check the API key storage/validation logic: does the key record have an owner/tenant/subject field, or is it just a shared secret compared with `==`/hash-compare against one static value?
- Search your auth middleware for how keys are issued -- grep for where keys are generated (`generate_api_key`, `create_key`) and check if the function takes a per-user/per-tenant parameter or is called once per deployment.
- Check access logs for the compromised key: can you tell which caller/IP/tenant is behind each request, or does the log only show "valid key used" with no distinguishing identity?
- Look for the key in client-side artifacts (mobile app binaries, frontend JS bundles, public repos) -- if a backend-scoped key is reachable from a public artifact, that's a structural issue independent of this specific leak.

## Fix
Move to per-principal API keys with a real lifecycle, not a single shared secret:
- Issue one key per user/tenant/service-integration, each stored as a row with an owner reference, creation date, and status (active/revoked), so revoking one key is a single-row update that doesn't touch others.
- Support key rotation with an overlap window: allow a new key to be issued and old key to keep working for a grace period (e.g. 24-48 hours) so the caller can migrate before the old key is hard-revoked, rather than instant cutover.
- Never embed a server-scoped secret in client-distributed code; if a mobile/frontend app needs to call your API, issue short-lived tokens via an authenticated exchange (e.g. the app authenticates the end user, backend mints a scoped, expiring token) instead of a static long-lived key.
- Add key usage metadata (last-used timestamp, calling IP ranges, request volume) so that when a leak is suspected, you can immediately answer "who has been using this key and what will break if I revoke it" instead of guessing.

## Pitfalls
Don't solve this by adding a second shared "backup key" that everyone falls back to when the first is revoked -- that just doubles the blast radius of the next leak instead of eliminating shared-secret risk. The fix is per-principal issuance, not more shared secrets.

## Verify
Pick one active integration, issue it a new per-tenant key through the new flow, confirm the old shared key still works for other tenants, then revoke only the new key and confirm exactly and only that one integration's calls start failing (401/403) while every other tenant's traffic is unaffected.
