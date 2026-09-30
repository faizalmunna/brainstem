---
name: jwt-expired-no-refresh-flow
description: Users are unexpectedly logged out mid-session because a short-lived JWT access token expires and no refresh-token flow silently renews it.
triggers: ["users get logged out randomly", "token expired error", "401 after 15 minutes", "jwt expired mid session", "why do users keep getting signed out"]
permissions: ["READ"]
---

## Symptom
Users report being logged out "randomly" -- often mid-form-submission or after leaving a tab open -- and the network tab shows a 401 with an "expired token"/`TokenExpiredError` message right before the logout. The session was valid minutes ago; nothing about the user's credentials changed. Correlate with the access token's `exp` claim: the logout always happens near (or slightly after) `exp`, meaning the client held a JWT past its validity window and had no way to get a new one.

## Likely causes
1. **No refresh token issued at all** -- the login response only returns a short-lived access token, so once it expires the client's only option is to force a full re-login, which the frontend implements as "log the user out" instead of a silent renewal.
2. **A refresh token exists but the client never calls the refresh endpoint** -- the frontend has no interceptor watching for 401s or proactively checking `exp` before it fires, so the expired token gets used until a request fails.
3. **The refresh endpoint exists but the access-token lifetime is too short relative to typical session/idle gaps** (e.g. 60-second access tokens with no background renewal), turning a normal usage pattern into constant expiry races.
4. **Refresh logic exists on web but is missing on a second client** (mobile app, third-party integration, server-to-server job) that reuses the same auth service, so the bug reproduces only on that one platform.
5. **Clock skew** between the auth server and API server causes tokens to be treated as expired earlier than intended, masquerading as a missing-refresh bug.

## Diagnose
- Decode the JWT from a failing request (base64-decode the payload, no signature verification needed for this) and compare its `exp` timestamp to the request's timestamp -- confirm the token was actually past expiry, not rejected for another reason (bad signature, wrong audience).
- Check the login/auth response schema: does it include a `refresh_token` (or set a refresh cookie) at all? If not, this is cause #1 and there's no client-side fix possible without a backend change.
- Search the frontend HTTP client setup for a 401-response interceptor or a proactive token-refresh timer. If neither exists, the refresh token (if issued) is simply never used.
- Check the access-token issuance code for the configured `exp` (or `expiresIn`) value and compare it against realistic session durations for this product.
- Reproduce on each client (web, mobile, CLI, backend job) independently -- if only one fails, the fix is scoped to that client's HTTP layer, not the auth server.

## Fix
Implement token refresh as a background contract between client and server, not a reactive patch: the auth server issues a long-lived refresh token alongside the short-lived access token; the client either (a) proactively refreshes shortly before `exp` using a timer derived from the decoded expiry, or (b) reactively catches a 401 with a token-expired reason, calls the refresh endpoint once, retries the original request with the new access token, and only forces logout if the refresh call itself fails (refresh token expired/revoked). Centralize this in one HTTP client interceptor/middleware so every request path (including background jobs and retries) goes through it, rather than reimplementing refresh-and-retry in each feature that calls the API.

## Pitfalls
Adding a naive "retry once on any 401" without checking the failure reason can create an infinite loop against endpoints that return 401 for reasons other than expiry (bad credentials, revoked access) -- always branch on a specific expired-token signal (an error code, not just the HTTP status) before attempting refresh. Also, firing concurrent refresh calls from multiple simultaneous failed requests (common right after a token expires and several requests are in flight) can race and invalidate each other if the server rotates the refresh token on use -- serialize refresh through a single in-flight promise/lock so parallel 401s share one refresh call.

## Verify
Set the access token's lifetime very short in a test environment (e.g. 30 seconds), stay logged in and idle past that window, then perform an action -- confirm the request succeeds transparently (a refresh call visible in the network tab, immediately followed by the original request succeeding) with no visible logout or user-facing error, and that only one refresh call fires even if multiple requests were in flight at expiry.
