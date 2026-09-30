---
name: dast-scan-blocked-by-login-wall
description: A DAST scan against staging reports a suspiciously small attack surface because it never authenticated past the login page.
triggers: ["dast scan only found the login page", "zap scan coverage is tiny", "dast can't get past authentication", "dynamic scan missing most of the app", "burp scan stuck at login"]
permissions: ["READ"]
---

## Symptom
A DAST tool (OWASP ZAP, Burp Suite, Invicti, Nuclei) runs against a
staging environment and completes "successfully" with a report showing
only a handful of URLs -- the login page, static assets, maybe a public
marketing route -- while the actual authenticated application (the vast
majority of the attack surface) was never crawled or tested at all, and
this goes unnoticed because the scan didn't error, it just silently
found less.

## Likely causes
1. **No authentication was configured for the scan at all** -- the
   crawler hits the login redirect, has no credentials to submit, and
   treats the login page as a dead end rather than a form to fill.
2. **Session-based auth breaks mid-scan** -- credentials were configured
   but the app issues a short-lived session token or CSRF token that
   expires or rotates faster than the scanner's session-renewal
   mechanism accounts for, so the scanner silently falls back to
   unauthenticated requests after the first few pages.
3. **Auth uses a mechanism the scanner's built-in form-auth doesn't
   handle** -- multi-step login (MFA, CAPTCHA, redirect through an
   identity provider like Okta/Auth0), meaning simple username/password
   form-fill scripts can't complete the flow at all.
4. **The scanner's "logged out" detection is misconfigured**, so even
   when auth briefly succeeds, the tool doesn't recognize being logged
   out mid-crawl (e.g. after hitting a logout link or triggering a
   server-side session invalidation) and continues crawling as if
   authenticated while actually receiving login-wall redirects.

## Diagnose
- Open the scan's request log/history (ZAP's HTTP History, Burp's
  Logger) and check what the actual HTTP responses were for the bulk of
  requests -- a wall of 302 redirects to `/login` or 401/403 responses
  is the direct signature of this failure, not a generic "low coverage"
  reading.
- Check the scan configuration for which auth method was set (form-based
  auth script, raw session token/cookie injection, OAuth flow) versus
  what the app actually requires -- compare against how a real user logs
  in manually in a browser.
- Manually replay the scanner's exact login request sequence (export
  from its history) in a REST client and check whether it returns a
  valid session cookie/token, isolating whether the problem is
  credential-submission or session-maintenance.
- Check the site map/crawl tree the tool produced -- if it's flat (a
  handful of top-level routes, no depth), that's consistent with the
  crawler bouncing off a login wall on every navigation attempt rather
  than genuinely finding a small app.

## Fix
Set up authentication explicitly and verify it out-of-band before
trusting a full scan: for simple form logins, configure the scanner's
form-based auth with the exact field names and a "logged-in indicator"
(a string or status code present only when authenticated, e.g. a
"Log out" link) so the tool can self-detect session loss and re-
authenticate mid-crawl; for token/session-cookie auth, script an
out-of-band login (via API or a headless browser step) that extracts a
valid session token and injects it as a fixed header/cookie for the
scan; for SSO/MFA-fronted apps, either carve out a test-only bypass
route in non-production environments (a backdoor login only reachable
in staging, never production) or use the scanner's browser-based
authenticated-scan mode that records a real login session (ZAP's
"Authentication via script" or a Selenium-driven login) rather than
relying on simple form-fill. Whichever mechanism is used, always
validate it produces a genuinely authenticated crawl before trusting
coverage numbers.

## Pitfalls
- Hardcoding a long-lived static session token into the scan config
  works short-term but silently goes stale (token expiry, password
  rotation) and produces the exact same failure mode weeks later with no
  alert -- pair static tokens with a coverage sanity check, not a
  one-time setup.
- Creating a permanent authentication bypass "just for scanning" and
  accidentally leaving it reachable in production is a more severe
  vulnerability than anything the DAST scan would have found --
  environment-gate any test-only auth shortcut explicitly.
- Trusting the scan's own "completed successfully" status as proof of
  coverage -- a scan that authenticates on request 1 and silently loses
  the session on request 2 still reports "completed," it just crawled
  almost nothing.

## Verify
Compare the post-fix crawl's site map against a manually maintained list
of known authenticated routes/features and confirm the scanner reached a
representative majority of them, and check the scan log for the ratio of
2xx responses to 401/403/redirect-to-login responses on requests after
the initial login -- a healthy authenticated scan should show sustained
2xx (or expected 4xx from deliberate negative tests) throughout, not a
reversion to login redirects partway through.
