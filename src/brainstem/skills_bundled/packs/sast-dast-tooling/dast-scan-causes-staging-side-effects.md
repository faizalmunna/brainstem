---
name: dast-scan-causes-staging-side-effects
description: A DAST scan against shared staging sends real emails, corrupts test data, or trips rate limits because it wasn't scoped away from stateful actions.
triggers: ["dast scan sent thousands of emails", "staging database full of scan junk", "scan triggered account lockouts", "dast scan crashed staging", "dynamic scanner spamming the password reset endpoint"]
permissions: ["READ"]
---

## Symptom
Running a DAST tool against a shared staging environment produces
real side effects beyond the scan itself: a flood of password-reset or
notification emails going out (sometimes to real addresses reused from
a production data snapshot), thousands of junk rows written into the
staging database, third-party sandbox accounts getting rate-limited or
locked out, or the environment becoming unusable for other QA/dev work
because the scanner exercised every form and mutating endpoint it could
crawl to indiscriminately.

## Likely causes
1. **The crawler treats every discovered endpoint as fair game by
   default**, including POST/PUT/DELETE routes and forms (password
   reset, "invite a colleague," checkout, account deletion) -- most DAST
   tools crawl and attack anything reachable unless explicitly told to
   exclude or treat certain paths as read-only.
2. **Staging uses production-like data** (a sanitized-in-theory but
   still real-looking copy, or worse, an unsanitized production
   snapshot) so scan traffic that hits an email/SMS/webhook integration
   fires against real third-party addresses or numbers instead of
   sandboxed test ones.
3. **No scope/exclusion list was configured before the first run** --
   the team pointed the scanner at the base URL and started the scan
   without an explicit include/exclude configuration, assuming
   "staging" implicitly meant "safe to hit anything."
4. **Active/aggressive scan policy used where a passive or scoped
   policy would do** -- DAST tools typically offer both passive
   (observe traffic, no attack payloads) and active (send attack
   payloads, follow every form) modes, and active mode against
   unscoped, stateful endpoints is what causes destructive side effects.

## Diagnose
- Check the scan's request log for HTTP methods used against known
  mutating endpoints (password reset, email invites, payment/checkout,
  account deletion) -- POST/PUT/DELETE requests logged against these
  routes during the scan window confirm the scanner exercised them.
- Check staging's outbound email/SMS provider logs (SendGrid, Twilio,
  whatever sandbox/relay is configured) for a volume spike correlated
  with the scan's start/end time.
- Check whether staging's environment configuration points any
  third-party integration (email, SMS, payment) at a real sandbox vs. a
  local mock/stub -- this determines whether "side effects" reach an
  actual external service at all.
- Review the scanner's run configuration for an exclude list, scan
  policy (active vs. passive), and authentication scope -- confirm none
  was set if this is the first run, which is the direct cause in most
  first-time-rollout incidents.

## Fix
Scope every DAST run explicitly before executing an active scan against
any shared environment: maintain an exclude list of known-destructive
paths (logout, delete-account, payment, bulk-email endpoints) that the
scanner should never touch, or better, run those with a passive-only
policy while active-scanning the rest; ensure staging's third-party
integrations point at sandboxed/mocked services (a test email provider
that captures rather than sends, a payment sandbox, not real SMS
credits) so that even a scan that does hit those endpoints has no
external-world effect; and where the scanner supports authenticated
role-based scanning, run it as a dedicated, clearly-labeled test account
so any data it creates is easy to identify and clean up afterward rather
than mixed indistinguishably into shared test data. For environments
that can't be made side-effect-safe, run DAST against an ephemeral,
disposable environment (a per-scan spun-up instance from CI) instead of
the shared, persistent staging environment.

## Pitfalls
- Excluding so many endpoints to avoid side effects that the scan no
  longer covers meaningful attack surface defeats the point of DAST --
  prefer making mutating endpoints safe to hit (sandboxed integrations,
  disposable data) over blanket exclusion where feasible.
- Assuming "staging" is inherently safe because it's not production --
  staging that shares real third-party credentials or a copied
  production database carries nearly the same blast radius as scanning
  production directly.
- Running the first-ever active scan against a shared environment during
  business hours without notifying the team that owns it -- even a
  well-scoped scan can produce enough load or transient data churn to
  disrupt others' concurrent testing.

## Verify
Re-run the scan with the exclude list and sandboxed integrations in
place, then confirm zero new entries in the real email/SMS provider's
send log during the scan window, and check the staging database for
scan-created records (they should be tagged/identifiable via the
dedicated test account) to confirm they're both present in expected,
scoped test tables and absent from anything that would leak into
shared/production-mirrored data views.
