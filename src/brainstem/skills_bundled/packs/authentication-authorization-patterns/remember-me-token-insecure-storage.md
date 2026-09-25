---
name: remember-me-token-insecure-storage
description: A long-lived remember-me or persistent-login token is stored in localStorage or readable JavaScript-accessible storage, turning any XSS into full account takeover.
triggers: ["remember me token in localstorage", "persistent login token xss risk", "long lived token accessible to javascript", "should auth token be in cookie or localstorage"]
permissions: ["READ"]
---

## Symptom
A security review flags that the app's "remember me" / persistent-login token (or, more broadly, any long-lived auth token) is stored in `localStorage`, `sessionStorage`, or another JavaScript-readable location, rather than an `httpOnly` cookie. On its own this isn't an active exploit, but it means any XSS vulnerability anywhere on the origin -- even one unrelated to auth, like an unescaped comment field -- can read and exfiltrate the token, and because it's long-lived (days to months, that's the point of "remember me"), a single successful script injection yields durable, replayable account access rather than a brief session.

## Likely causes
1. **SPA architecture stored the token in `localStorage` for convenience** -- it's simple to read (`localStorage.getItem`) and attach to API calls manually as an `Authorization: Bearer` header, especially when the API and frontend are on different origins/ports during development, and the team never revisited it for the persistent/long-lived token specifically.
2. **A cross-origin setup made cookies seem harder** -- the frontend and API are on different domains, and someone concluded cookies "don't work" cross-origin and reached for `localStorage` instead, without exploring `SameSite=None; Secure` cookies or a same-site proxy.
3. **The short-lived access token and the long-lived remember-me/refresh token were treated identically** -- a decision (reasonable or not) to accept some XSS exposure for a short-lived access token got applied uniformly to the much higher-stakes long-lived token without separately reconsidering the risk.
4. **Mobile/hybrid app parity assumptions** -- a team storing tokens in a mobile app's local storage (a different threat model, no arbitrary script injection risk in the same way) applied the same pattern to the web client without accounting for XSS.

## Diagnose
- Search the frontend codebase for where the persistent/remember-me or refresh token is written and read (`localStorage.setItem`, `sessionStorage`, or a JS-readable cookie i.e. one set without `HttpOnly`) and confirm its actual lifetime (check the token's `exp` or the DB record's expiry) to establish how long a stolen copy would remain valid.
- Check whether any user-generated content is rendered without sanitization anywhere on the same origin (comments, profile fields, markdown rendering) -- even one such gap combined with JS-readable long-lived tokens is a full compromise path, not just a theoretical one.
- Confirm whether cookies are actually infeasible for the architecture, or just assumed to be: check if frontend and API could share a registrable domain (or go through a same-site proxy/BFF) to make `httpOnly` cookies viable.

## Fix
Store any long-lived credential (remember-me token, refresh token) in an `HttpOnly`, `Secure`, `SameSite=Lax` or `SameSite=None; Secure` (for legitimate cross-site needs) cookie, so it's sent automatically by the browser but never readable by JavaScript -- meaning an XSS bug can still make requests *as* the user in that moment, but can't exfiltrate a durable, replayable credential to use later or elsewhere. Where cross-origin cookies genuinely can't be made to work, prefer a backend-for-frontend (BFF) pattern: the browser holds only a same-site session cookie, and the BFF server-side holds and uses the actual long-lived token, keeping it out of the browser entirely. Reserve short-lived, in-memory (not even localStorage) storage for access tokens if a non-cookie transport is unavoidable for API calls, and never extend that pattern to the long-lived token.

## Pitfalls
Switching storage to a cookie but leaving off `HttpOnly` (common when the frontend still wants to read the cookie's value directly in JS "just in case") defeats the entire point of the change -- verify the flag is actually present, not just that storage moved to a cookie. Also, moving the *access* token to a cookie while leaving a separate long-lived remember-me token in localStorage because "it's a different code path" only half-fixes the actual risk, since the long-lived one is the higher-value target.

## Verify
Inspect the `Set-Cookie` header (or run `document.cookie` and confirm the token doesn't appear) to verify the long-lived token is not accessible via JavaScript at all; then, with a benign injected script (in a test/staging environment) attempt `document.cookie` and `localStorage` reads and confirm neither exposes the persistent credential.
