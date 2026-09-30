---
name: api-auth-token-vs-session
description: Choose between session-cookie and token (JWT/opaque) authentication for an API, and diagnose the specific bugs each approach commonly produces.
triggers: ["jwt vs session", "token auth bug", "session auth vs jwt", "cant revoke jwt", "auth token expired unexpectedly", "cors credentials auth issue"]
permissions: ["READ"]
---

## Symptom
Either a design question ("should this API use sessions or tokens?") or
one of the specific bugs each approach produces: JWTs that can't be
revoked before they expire, session cookies that don't work across
subdomains/CORS, or a token refresh flow that logs users out unexpectedly.

## Likely causes (when diagnosing a bug, not choosing a scheme)
1. **JWT revocation gap**: a JWT was issued with a long expiry and the
   system has no way to invalidate it early (password change, logout,
   compromised token) short of waiting for natural expiry -- this is an
   inherent property of stateless tokens, not a bug in one specific
   implementation, but often surprises teams who expect "logout" to
   actually invalidate the token everywhere.
2. **Cookie-based sessions failing cross-origin/cross-subdomain** due to
   `SameSite`/`Secure`/`Domain` cookie attributes not matching the actual
   deployment topology (API on a different subdomain or origin than the
   frontend).
3. **Refresh-token race condition**: two concurrent requests both detect
   an expired access token and both attempt to refresh, and the second
   refresh (using an already-rotated/invalidated refresh token) fails,
   logging the user out even though the first refresh succeeded.
4. **Storing tokens insecurely on the client** (JWT in `localStorage`,
   accessible to any XSS) versus a cookie-based session with `HttpOnly`,
   changing the actual attack surface without the team having made that
   trade-off deliberately.

## Diagnose
- For "can't log a user out," check whether the auth scheme is stateless
  JWT with no server-side revocation list/short expiry, which is
  expected behavior for that design, not a bug -- the fix is a design
  change (see below), not a patch.
- For cross-origin cookie failures, inspect the `Set-Cookie` response
  header's `SameSite`, `Secure`, and `Domain` attributes against the
  actual frontend/API origins in the deployment.
- For refresh race conditions, reproduce with two near-simultaneous
  requests after token expiry and check whether the second refresh
  attempt uses a refresh token already invalidated by the first.

## Fix
- **Choosing a scheme**: use cookie-based sessions (with `HttpOnly`,
  `Secure`, appropriate `SameSite`) for first-party web apps served from
  a domain the API trusts -- simpler revocation (delete the server-side
  session) and better XSS protection. Use tokens (JWT or opaque, via an
  `Authorization` header) for APIs consumed by third parties, mobile
  apps, or genuinely cross-origin SPAs where cookies don't fit cleanly.
- **JWT revocation**: keep JWT expiry short (minutes, not days) and pair
  it with a refresh-token flow where the refresh token *is* checked
  against a server-side store on each use -- this gives you a real
  revocation point (invalidate the refresh token) without making every
  request hit the database.
- **Cross-origin cookies**: set `SameSite=None; Secure` explicitly when
  the frontend and API are on different origins that need to share the
  session, and ensure the frontend sends `credentials: 'include'` on
  requests.
- **Refresh races**: make refresh-token rotation idempotent for a short
  grace window (accept the immediately-previous refresh token once more
  if a rotation just happened), or serialize refresh attempts client-side
  so concurrent requests share one in-flight refresh instead of each
  trying independently.

## Pitfalls
- Storing a JWT in `localStorage` "because it's simpler than cookies"
  trades CSRF protection for XSS exposure -- any injected script can read
  and exfiltrate it; this should be a deliberate, documented choice, not
  a default.
- Treating a long-lived JWT's lack of revocation as acceptable "because
  it hasn't been a problem yet" leaves no way to respond to an actual
  incident (compromised token, terminated employee) until it naturally
  expires.
- Adding a token blacklist/revocation list to "fix" stateless JWTs
  reintroduces a server-side state check on every request, which erases
  the main performance benefit of using JWTs in the first place -- at
  that point, a session store was probably the simpler design.

## Verify
For a revocation fix, confirm that invalidating a session/refresh token
server-side (simulating logout or a security response) actually prevents
a subsequent request presenting the old credential from succeeding,
within the intended time bound (immediately for sessions, within one
refresh cycle for the JWT+refresh-token approach).
