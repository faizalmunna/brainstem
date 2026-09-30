---
name: session-fixation-on-login
description: A session ID issued before login remains valid and unchanged after authentication, letting an attacker who planted that ID hijack the logged-in session.
triggers: ["session fixation vulnerability", "session id unchanged after login", "attacker pre-set session cookie hijack", "session not regenerated on authentication"]
permissions: ["READ"]
---

## Symptom
Found via security testing or audit: capture the session cookie/ID *before* logging in (a fresh, unauthenticated visit), then log in normally, and observe that the session ID stays exactly the same before and after authentication -- only its associated permissions/user data change server-side. This means anyone who can get a victim to use a known session ID before they log in (via a crafted link, a shared/public terminal, or a subdomain that can set cookies for the parent domain) can then use that same ID to ride along as the victim once they authenticate.

## Likely causes
1. **The session object is created once at first visit and simply updated in place on login** -- the login handler sets `session['user_id'] = ...` on the existing session without ever calling the framework's session-regeneration function, so the session identifier itself never changes.
2. **A framework/library default was overridden or misunderstood** -- many frameworks regenerate session IDs on login by default, but a custom auth flow (SSO callback handler, a legacy login endpoint, a password-reset auto-login) was written separately and doesn't go through the code path that triggers regeneration.
3. **Session ID is derived from something stable and attacker-visible** (e.g. a value set via a URL parameter that gets echoed into a cookie, or a predictable token) rather than a fresh cryptographically random value generated server-side at each privilege-level change.
4. **Regeneration happens but the old session ID isn't invalidated**, only a new one is issued alongside it -- so the pre-login session ID (the one an attacker may have planted) still maps to the now-authenticated session.

## Diagnose
- With devtools/an HTTP client, record the session cookie value on an unauthenticated page load, complete login, and compare the session cookie value after login -- any framework or manual auth code should be issuing a *new* identifier at this point.
- Grep the login/authentication success handler for a call to the framework's session regeneration function (e.g. `regenerate()`, `cycle_key()`, `session.regenerate_id()`, or equivalent) and confirm it's actually invoked before setting authenticated session data.
- Check every distinct way a user can become authenticated (standard login, SSO callback, magic-link click, password-reset auto-login, "impersonate user" admin tooling) independently -- fixation bugs often exist on the less-traveled auth paths even after the main login form is fixed.
- Attempt the full fixation scenario end-to-end: set a known session ID (via cookie or whatever mechanism the app uses) in one browser context, have a separate "victim" context log in using default handling, then check from the original context whether it now has authenticated access.

## Fix
On every transition to a higher privilege level -- login success, privilege elevation (e.g. re-auth for a sensitive action), and ideally logout too -- generate a brand-new session identifier and invalidate the old one, migrating the necessary session data (or discarding it, for login) to the new ID rather than reusing the pre-existing session record. Use the framework's built-in regeneration mechanism rather than hand-rolling it, and make sure this call sits in the one shared "authentication succeeded" code path that every login method (password, SSO, magic link, admin impersonation) routes through, rather than duplicated per method.

## Pitfalls
Regenerating the session ID but forgetting to invalidate the old one server-side leaves a window where both the old (attacker-planted) and new session IDs are valid simultaneously, defeating the fix. Also, if session data (like a shopping cart or in-progress form) is deliberately preserved across the regenerated ID, make sure only non-sensitive data carries over -- copying an authorization-relevant flag from the old, potentially attacker-influenced session into the new authenticated one can reintroduce a related trust bug.

## Verify
Automate the fixation scenario as a regression test: capture a session identifier before authentication, complete login, and assert the post-login identifier differs from the pre-login one; then replay the pre-login identifier in a separate request and confirm it is rejected or treated as an anonymous/unauthenticated session, not the now-logged-in one.
