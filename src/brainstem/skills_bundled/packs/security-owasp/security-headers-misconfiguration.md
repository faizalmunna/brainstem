---
name: security-headers-misconfiguration
description: Diagnose missing or misconfigured HTTP security headers (CSP, HSTS, X-Frame-Options, etc.) and set them to values that actually protect without breaking the app.
triggers: ["missing security headers", "csp misconfigured", "hsts not set", "clickjacking", "x-frame-options missing", "security headers scan failed"]
permissions: ["READ"]
---

## Symptom
A security scanner (Mozilla Observatory, securityheaders.com, an internal
audit) flags missing or weak HTTP response headers, or a specific
incident traces back to one: a site can be framed by another origin
(clickjacking), a man-in-the-middle can downgrade HTTPS to HTTP on first
visit, or an injected script executes despite other XSS defenses because
no Content-Security-Policy restricts it.

## Likely causes
1. **No `Content-Security-Policy` header at all**, or one so permissive
   (`default-src *`, `unsafe-inline` allowed broadly) that it provides
   little real restriction on script/resource sources.
2. **No `Strict-Transport-Security` (HSTS)**, leaving a window on the
   user's *first* visit (before any redirect to HTTPS) where a network
   attacker could intercept a plain-HTTP request.
3. **No `X-Frame-Options` (or CSP `frame-ancestors`)**, allowing the site
   to be embedded in an iframe on an attacker's page for clickjacking
   attacks (tricking users into clicking something they can't see).
4. **`X-Content-Type-Options: nosniff` missing**, allowing some browsers
   to MIME-sniff a response into a different, more dangerous content type
   than declared.
5. **Headers set inconsistently across different services/routes**
   (a reverse proxy sets them for most routes but a specific
   service/microservice behind it doesn't), so the gap only shows up on
   certain endpoints.

## Diagnose
- Check actual response headers (`curl -I`, browser devtools, or a
  scanner) for the specific application's real production responses --
  not just what's declared in application code, since a reverse
  proxy/CDN in front of it may add, remove, or override headers.
- For CSP specifically, check whether it's present and how permissive it
  actually is (`unsafe-inline`, `unsafe-eval`, wildcard sources)
  rather than just checking for the header's existence.
- Check consistency across different routes/services -- a header set at
  one layer (app framework default) may not apply uniformly if a specific
  route bypasses that middleware, or if multiple backend services exist
  behind a shared entry point with inconsistent configuration.

## Fix
- Set `Content-Security-Policy` restricting script/style/resource sources
  to explicitly known-needed origins, avoiding `unsafe-inline`/
  `unsafe-eval` where possible (moving inline scripts to external files
  or using nonces/hashes for the specific inline scripts that are
  genuinely needed).
- Set `Strict-Transport-Security` with a meaningful `max-age` (and
  `includeSubDomains`/`preload` if appropriate for the domain's actual
  subdomain structure) once HTTPS is confirmed to work correctly across
  the whole site -- enabling HSTS incorrectly before HTTPS is fully
  reliable can lock users out if the certificate/config has issues.
- Set `X-Frame-Options: DENY` (or `SAMEORIGIN` if legitimate same-origin
  framing is needed) or the equivalent CSP `frame-ancestors` directive.
- Set `X-Content-Type-Options: nosniff` and other standard headers
  (`Referrer-Policy`, `Permissions-Policy`) appropriate to the
  application's actual needs.
- Apply headers at the layer that guarantees consistency across every
  route/service (a shared reverse proxy/gateway configuration, or a
  framework-wide middleware applied globally) rather than per-route,
  specifically to avoid the "works on most routes" gap.

## Pitfalls
- Deploying a strict CSP without first auditing what the application
  actually needs (inline scripts, third-party embeds, analytics scripts)
  will break real functionality -- roll out via `Content-Security-Policy-
  Report-Only` first to see what a strict policy would have blocked,
  before enforcing it.
- Enabling HSTS with `preload` is very hard to reverse (browsers hardcode
  preloaded domains) -- don't add `preload` until HTTPS reliability is
  thoroughly confirmed across the entire domain and all subdomains it
  would apply to.
- Setting headers only in application code when a CDN/reverse proxy sits
  in front can result in the proxy stripping or overriding them --
  verify what actually reaches the browser, not just what the
  application emits.

## Verify
Check actual production response headers (not local dev) for the
specific headers and their values, confirm a CSP violation report (if
using report-only mode first) doesn't show unexpected breakage before
switching to enforce mode, and re-run the original scanner/audit to
confirm the specific findings are resolved.
