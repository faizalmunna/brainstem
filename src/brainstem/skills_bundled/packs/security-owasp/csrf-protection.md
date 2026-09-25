---
name: csrf-protection
description: Diagnose missing CSRF protection on state-changing requests, and choose the right defense (token vs SameSite cookies) for the actual auth scheme in use.
triggers: ["csrf", "cross site request forgery", "state changing request no token", "samesite cookie", "csrf token missing"]
permissions: ["READ"]
---

## Symptom
A state-changing action (changing a password, transferring funds, making
a purchase) can be triggered by a request originating from a different,
attacker-controlled site while the victim is authenticated in another
tab -- the browser automatically attaches the victim's session cookie,
and the server has no way to distinguish a legitimate same-site request
from a cross-site forged one.

## Likely causes
1. **No CSRF token (or equivalent) on state-changing form
   submissions/API calls**, relying solely on the session cookie being
   present -- cookies are sent automatically by the browser regardless of
   which site initiated the request, so cookie presence alone doesn't
   prove the request was intentional.
2. **Cookie `SameSite` attribute not set (or set to `None`)** for a
   session cookie that's meant to be first-party-only, allowing it to be
   sent on cross-site requests.
3. **A CSRF token present on the main web form but missing on a secondary
   path reaching the same action** (an API endpoint used by a mobile app
   that shares the session mechanism, a "quick action" link, a webhook-
   style callback) -- protection applied inconsistently across the
   surface area.
4. **Token validated for presence but not for correctness** (an endpoint
   checks a CSRF token field exists but doesn't actually verify it
   matches the expected value tied to the session) -- looks protected in
   code review, isn't in practice.
5. **GET requests used for state-changing actions**, which are
   trivially triggerable cross-site via a simple `<img>`/link with no
   token mechanism typically applied to GET at all.

## Diagnose
- For the specific state-changing endpoint, check whether it validates a
  CSRF token (or relies on `SameSite=Strict`/`Lax` cookies as the primary
  defense) and whether that validation is actually enforced, not just
  present as an unused field.
- Check the cookie's `SameSite` attribute value directly (via browser
  devtools or the `Set-Cookie` response header).
- Grep for other endpoints performing state changes (not just the
  originally reported one) and check each independently for the same
  protection.
- Confirm no state-changing action is reachable via a plain `GET` request.

## Fix
- Implement synchronizer-token-pattern CSRF protection for session-cookie-
  authenticated state-changing requests: a per-session (or per-request)
  token embedded in forms/API calls and validated server-side against the
  session on every state-changing request.
- Set `SameSite=Lax` (or `Strict` where it doesn't break legitimate
  cross-site navigation flows the app needs) on session cookies as a
  strong complementary defense -- modern browsers default new cookies to
  `Lax` if unset, but verify this explicitly rather than relying on a
  browser default that could change.
- Ensure every state-changing endpoint (not just the main web UI's forms)
  enforces the same protection, including secondary/mobile/API paths that
  share the session mechanism.
- Move any state-changing action currently reachable via `GET` to a
  method that isn't trivially cross-site-triggerable (`POST`/`PUT`/
  `DELETE` combined with the token/SameSite protections above).

## Pitfalls
- Token-based CSRF protection is largely unnecessary (though still
  reasonable as defense-in-depth) for APIs authenticated purely via a
  bearer token in an `Authorization` header rather than cookies, since
  browsers don't automatically attach arbitrary headers to cross-site
  requests the way they do cookies -- know which auth mechanism is
  actually in play before assuming CSRF tokens are the right primary fix.
- `SameSite=Strict` can break legitimate flows where a user navigates to
  the site from an external link while relying on their existing session
  (e.g. clicking a link from an email) -- `Lax` is usually the right
  default balance unless the specific flow has been verified not to need
  cross-site-initiated navigation with cookies attached.
- Validating "a token was submitted" without validating it matches the
  session's expected value provides no real protection -- verify the
  actual comparison logic, not just the field's presence.

## Verify
Construct a cross-site request (a simple HTML form on a different origin,
submitted from a browser with an active session) targeting the fixed
endpoint and confirm it's rejected, while the same action performed from
the application's own legitimate UI still succeeds.
