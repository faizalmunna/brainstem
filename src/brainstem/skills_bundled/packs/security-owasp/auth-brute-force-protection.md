---
name: auth-brute-force-protection
description: Add rate-limiting/lockout to authentication endpoints without locking out legitimate users or leaking whether a given username/email exists.
triggers: ["login brute force", "credential stuffing", "no rate limit on login", "account lockout policy", "password spray attack"]
permissions: ["READ"]
---

## Symptom
A login (or password-reset, or MFA-code-verification) endpoint accepts
unlimited attempts with no meaningful slowdown or lockout, making it
practical to brute-force a weak password or run credential-stuffing
(trying leaked username/password pairs from other breaches) at scale
against real accounts.

## Likely causes
1. **No rate limiting at all on authentication endpoints** -- unlike
   general API rate limiting (covered in `api-rate-limiting-design`),
   authentication endpoints have specific, higher-stakes requirements:
   the cost of under-protecting is account takeover, not just service
   load.
2. **Rate limiting keyed only on IP address**, which credential-stuffing
   tools routinely evade by rotating IPs across many attempts, while
   still under-protecting nothing if the limiting is otherwise reasonable
   per-IP.
3. **Account lockout that reveals account existence** -- a "too many
   attempts, account locked" message shown only when the *username* is
   valid (but not when it's invalid) lets an attacker enumerate valid
   accounts even without ever guessing a correct password.
4. **Lockout with no unlock mechanism other than a slow manual process**,
   creating a denial-of-service vector where an attacker locks out
   legitimate users just by attempting logins with their usernames and a
   wrong password.
5. **No protection on adjacent flows** -- password reset request, MFA
   code verification, and "resend code" endpoints often get overlooked
   even when the main login form is protected.

## Diagnose
- Check whether the login endpoint (and password-reset, MFA-verification,
  and "resend code" endpoints) has any rate limiting or lockout at all,
  and what it's keyed on.
- Check whether the response differs in a way that leaks account
  existence (different error message, different timing, an explicit
  "account locked" state) between a valid username with a wrong password
  and an invalid username entirely.
- Check what happens after a lockout triggers: is there a time-based
  auto-unlock, a step-up challenge (CAPTCHA), or does it require manual
  intervention that a legitimate locked-out user has no fast path
  through?

## Fix
- Apply rate limiting combined across multiple keys: per-IP (catches
  single-source brute force), per-account/username (catches distributed
  credential stuffing against one target), and consider a global
  anomaly-detection layer for large-scale distributed attempts across
  many accounts from many IPs.
- Use identical response messages and response timing for "wrong
  password" and "account doesn't exist," so failed-login responses don't
  leak account existence -- test this specifically, since timing
  differences (a real password-hash comparison taking longer than an
  early-exit for a nonexistent user) can leak the same information even
  when the message text is identical.
- Prefer progressive friction (increasing delay, then a CAPTCHA
  challenge) over a hard lockout that a legitimate user can't recover
  from quickly -- and if using lockout, always after a real risk
  threshold, with an automatic time-based unlock in addition to (not
  instead of) a manual override.
- Apply the same protection to password-reset request, MFA-verification,
  and code-resend endpoints -- audit the whole authentication flow, not
  just the primary login form.

## Pitfalls
- Hard account lockout with no auto-unlock creates a denial-of-service
  vector: an attacker who knows (or guesses) a valid username can lock
  the real user out just by making enough failed attempts, with no
  correct password needed.
- Rate limiting purely by IP is trivially evaded by IP rotation for
  automated credential-stuffing tools -- per-account limiting is the
  more important half of the combination for this specific threat.
- CAPTCHA and similar friction on every single login attempt (rather than
  triggered progressively after suspicious activity) hurts legitimate
  user experience for no added protection against the actual threat --
  apply friction proportionally, not unconditionally.

## Verify
Simulate a burst of failed login attempts against a test account from a
single source and confirm rate limiting/friction kicks in as designed;
separately, confirm that failed-login responses for a valid username with
a wrong password and a nonexistent username are indistinguishable in both
message and response timing.
