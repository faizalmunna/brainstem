---
name: jwt-revocation-not-enforced
description: Logging out, disabling an account, or revoking access has no real effect because a stateless JWT keeps passing verification until it naturally expires.
triggers: ["logout doesn't invalidate jwt", "disabled user can still access api with old token", "revoked token still works", "jwt blocklist not checked", "can't force logout of stolen token"]
permissions: ["READ"]
---

## Symptom
An admin disables a user's account, or the user explicitly logs out, or a security incident requires force-invalidating a specific token -- and yet requests bearing the old JWT keep succeeding until the token's `exp` naturally arrives. Logging out client-side (deleting the token from the browser) appears to work for that one browser, but the same token, if it were saved elsewhere (another device, an intercepted copy, a browser history/cache), remains fully functional.

## Likely causes
1. **The system is purely stateless by design** -- JWTs were chosen specifically to avoid a server-side lookup on every request, so there is genuinely no revocation check anywhere in the verification path; "logout" only ever meant "the client stops sending the token," never "the server stops accepting it."
2. **A blocklist/revocation table exists but isn't consulted at verification time** -- there's a `revoked_tokens` table populated on logout/disable, but the auth middleware only checks the signature and expiry, never querying it.
3. **Revocation is checked for logout but not for other revocation triggers** -- explicit logout clears things correctly, but disabling a user account, changing their password, or an admin-forced "log out everywhere" doesn't feed into the same revocation mechanism.
4. **Revocation list checked inconsistently across services** in a microservices setup -- the main API checks a shared blocklist, but a second service verifying the same JWTs independently (for its own endpoints) doesn't share that check.
5. **Long-lived access tokens make the problem severe** even where revocation *is* implemented for refresh tokens -- rotating/revoking the refresh token doesn't touch an already-issued access token that's still within its (long) validity window.

## Diagnose
- Log out (or have an admin disable/deactivate a test account) and then replay the previously-issued access token directly against a protected endpoint (via curl/Postman, bypassing the now-logged-out browser) -- confirm whether it still succeeds.
- Check the token verification middleware for any lookup against a revocation store (Redis set, DB table, or short-lived deny-list) versus only checking signature and `exp`.
- If a revocation mechanism exists, trace which events actually write to it: logout, account disable, password change, admin force-logout, token-theft response -- and which of those don't.
- In a multi-service architecture, check whether every service that independently verifies the JWT consults the same shared revocation store, or whether each has its own auth middleware with different behavior.
- Check the access token's configured lifetime; a long-lived access token (hours+) makes any revocation gap far more consequential than a short-lived one paired with revocable refresh tokens.

## Fix
Decide deliberately how much revocability the system needs and design accordingly, rather than discovering the gap in production: keep access tokens short-lived (minutes) so their un-revocable window is small, and enforce all real revocation (logout, disable, force-logout-everywhere, incident response) against the *refresh* token, which should be a stateful, server-side-checked record you can actually delete or flag revoked. If immediate revocation of access tokens themselves is a hard requirement (e.g. for compliance or high-risk actions), add an explicit, fast revocation check to the verification path -- a small, low-latency store (Redis with TTL matching token expiry, so entries self-clean) checked on every request -- accepting the added lookup cost as the tradeoff for that guarantee, and make sure every service verifying these tokens shares that same store.

## Pitfalls
Implementing a blocklist keyed by user ID instead of by specific token/session can be overly broad (revoking one session logs the user out of all their other legitimate devices) or, if implemented as "check user's `disabled` flag" without a token-level check, still won't stop a token issued *before* disabling from working until it naturally expires. Also, adding a revocation check but forgetting to apply it in every service or code path that independently verifies the same JWTs leaves a bypass through whichever path was missed.

## Verify
Issue a token, revoke it (via logout, account disable, or explicit revocation) through each supported revocation trigger in the system, and for each one replay the original token directly against a protected endpoint (not through the UI, which may just be hiding the token) and confirm it's rejected immediately, not just after natural expiry.
