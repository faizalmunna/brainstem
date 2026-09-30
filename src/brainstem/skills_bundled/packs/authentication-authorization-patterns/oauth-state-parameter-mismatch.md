---
name: oauth-state-parameter-mismatch
description: An OAuth2 authorization code flow intermittently fails with a state mismatch error even though the user completed a legitimate login.
triggers: ["state parameter mismatch", "oauth callback fails randomly", "csrf state error on login", "invalid state oauth2", "login works sometimes but not always with google/github sso"]
permissions: ["READ"]
---

## Symptom
Users occasionally hit an "invalid state" or "state mismatch" error on the OAuth2 callback (`/callback?code=...&state=...`) right after a legitimate login through Google/GitHub/etc. It isn't consistent -- most logins succeed, but a noticeable fraction fail, often correlated with slow logins, multiple tabs, back-button use, or mobile browsers. Because `state` exists specifically as CSRF protection, the naive read is "someone's under attack," but the actual pattern (real users, real credentials, intermittent) points to the state being lost or overwritten client-side, not tampered with.

## Likely causes
1. **State stored in a place that isn't stable across the redirect round-trip** -- e.g. an in-memory variable, a Redux store, or `sessionStorage` scoped to a tab that gets replaced when the IdP redirect opens a new tab/window instead of navigating the same one.
2. **State stored server-side keyed by session, but the session cookie itself doesn't survive the redirect** -- e.g. `SameSite=Strict` (or a missing `SameSite=None; Secure` for cross-site redirect flows) drops the cookie on the return leg from the IdP's domain, so the server can't find the state it originally stored.
3. **Multiple concurrent login attempts overwrite each other's stored state** -- a user double-clicks "Login with Google," or opens the login page in two tabs, and the second request's state overwrites the first in a single shared storage slot (one cookie/session key, not one per attempt).
4. **State value expires too quickly** relative to how long users actually take on the IdP's consent screen (entering 2FA, choosing an account, reading a consent prompt), so slow-but-legitimate logins outlive a short TTL.
5. **A caching/CDN layer or load balancer routes the callback request to a different backend instance** than the one that generated the state, and state is held in that instance's local memory rather than a shared store.

## Diagnose
- Reproduce with browser devtools open: check whether the state value sent in the initial authorize redirect matches what's stored (cookie/session/localStorage) at the moment of redirect, and again what's present when the callback fires.
- Inspect the `Set-Cookie` header from the authorize step for `SameSite` and `Secure` attributes, and confirm in the Network tab whether that cookie is actually being sent on the callback request (cross-site redirects require `SameSite=None; Secure`).
- Check whether state storage is per-attempt (a random key per login click) or a single shared slot -- grep the auth code for how/where the state is written just before generating the authorize URL.
- If running multiple backend instances, check whether state is stored in local process memory vs. a shared store (Redis, DB, or a signed/stateless value) -- restart or scale-test to see if failures correlate with instance count.
- Time a few slow, deliberate logins (pause on the IdP consent screen) against the configured state TTL to see if expiry is the culprit.

## Fix
Treat `state` as short-lived, per-attempt, transport-independent data: generate a fresh random value per login attempt, bind it to that attempt only (never a single shared slot that a second attempt can clobber), and store it somewhere that reliably survives the full redirect round-trip -- either a signed, stateless value (HMAC the state itself, or encode it as part of a signed cookie so no server-side lookup is needed) or a shared, cross-instance store keyed by the state value itself rather than by session. If using a cookie to carry state across the redirect, set `SameSite=None; Secure` (required for the browser to send it back after navigating away to the IdP and returning) rather than the default `Lax`/`Strict`, and give it a TTL generous enough to cover slow consent screens and 2FA (several minutes, not seconds).

## Pitfalls
Reacting to intermittent state failures by simply removing or weakening the state check ("just skip validation if it's missing") eliminates the CSRF protection state exists to provide, turning a reliability bug into a security hole -- the fix is to make state storage reliable, not to stop checking it. Also, switching to a stateless signed-state approach without an expiry/nonce-reuse check reintroduces replay risk: a signed state token still needs a short TTL and single-use enforcement (or binding to the PKCE verifier) to retain its CSRF-protection value.

## Verify
Run the full login flow with artificial latency on the IdP consent step (or manually pause before approving) at least as long as real users' slowest observed logins, across a cross-site cookie setup (different eTLD+1 between app and IdP domains) and confirm the callback succeeds; also fire two login attempts back-to-back from the same browser and confirm both complete independently without one invalidating the other's state.
