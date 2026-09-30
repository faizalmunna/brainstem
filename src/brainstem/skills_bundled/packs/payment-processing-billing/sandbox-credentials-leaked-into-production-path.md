---
name: sandbox-credentials-leaked-into-production-path
description: Real customer checkouts silently fail or test charges appear to succeed because sandbox and production payment API keys are mixed up in a specific environment or code path.
triggers: ["test api key used in production", "live payments not going through", "sandbox charges look successful but no money moved", "wrong stripe key in prod"]
permissions: ["READ"]
---

## Symptom
Two related but distinct failure patterns: either (a) production checkout
silently fails or behaves oddly for real customers because a test/sandbox
API key or endpoint is being used in the live path, so charges never
actually process against real money even though the application shows a
generic error or, worse, a false success; or (b) a staging/test
environment is accidentally configured with live production credentials,
so QA or automated tests create real charges against real customer cards
or the company's live payment account.

## Likely causes
1. **Environment variables for API keys are misconfigured per
   environment** -- a deploy pipeline or secrets manager has the
   test/live keys swapped between the staging and production
   environment definitions, often introduced when a new environment is
   cloned from an existing one without updating the credential values.
2. **The application selects test-vs-live mode based on a different
   signal than the one actually driving key selection** -- e.g. a
   `NODE_ENV`/`APP_ENV` flag controls UI behavior and logging verbosity,
   but the payment SDK is initialized from a hardcoded key or a
   differently-named config variable that wasn't updated when the
   environment flag was introduced, so the two silently diverge.
3. **A feature flag or per-request override intended for internal testing
   in production** (e.g. "use sandbox mode for this specific test
   account") leaks to real users because the condition that gates it is
   too broad or has a bug (e.g. matches on a substring of an email domain
   rather than an exact internal test-account allowlist).
4. **Client-side (publishable/public) key and server-side (secret) key
   are sourced from different configs and only one was updated** when
   rotating from test to live -- many providers use a public/private key
   pair, and a mismatched pair (public live + secret test, or vice versa)
   produces confusing partial failures rather than an obvious outright
   error.

## Diagnose
- Check the actual key prefix/format being used in each environment at
  request time (most providers prefix test and live keys differently,
  e.g. `sk_test_`/`sk_live_` or `pk_test_`/`pk_live_`) -- log or
  temporarily print the key prefix (never the full key) at payment-client
  initialization in each environment to confirm which mode is actually
  active, rather than trusting the environment variable's *name*.
- Cross-reference: does the environment that's supposed to be live show
  any transactions in the provider's live dashboard for the time window in
  question, and does the environment that's supposed to be test show
  matching transactions in the test dashboard? A live environment with
  zero live-dashboard transactions during active traffic is the
  smoking gun for reversed keys.
- Check whether the public/client-side key and the secret/server-side key
  belong to the same mode by inspecting both prefixes -- providers
  typically reject a request outright if they're mismatched, but some
  operations (tokenization) can partially succeed with a mismatched pair
  before failing later, producing confusing partial-failure symptoms.
- Audit the deploy/secrets configuration diff between environments (not
  just today's state, but what changed recently) if this appeared after a
  recent deploy or environment change.

## Fix
Make the test-vs-live decision derive from exactly one source of truth per
environment (a single environment variable read at application startup,
not a per-file or per-module assumption), and fail loudly at startup --
not at first checkout attempt -- if the key's own prefix doesn't match the
expected mode for that environment (i.e. assert `sk_live_` is present when
`APP_ENV=production`, and refuse to boot otherwise). Keep test and live
credentials in clearly separate secrets-manager paths/namespaces with
access controls that make it structurally harder to paste a live key into
a staging config (e.g. staging service accounts simply have no read
access to the live secrets path). For any internal "force sandbox mode"
override, gate it on an exact allowlist of internal account IDs checked
server-side, never on a pattern match against user-controllable data like
an email domain.

## Pitfalls
- Adding a startup assertion that only checks the secret key's prefix and
  not the publishable/public key -- a mismatched pair can still slip
  through and produces its own distinct partial-failure mode.
- Treating this as a one-time fix after finding it once -- without a
  structural safeguard (the startup assertion, or secrets-path isolation),
  the same class of mistake reintroduces itself on the next environment
  clone or credential rotation.
- Rotating a leaked live key without also checking whether any charges
  were actually made against it during the misconfiguration window --
  fixing the configuration doesn't undo real charges that may need
  refunding, or missing test charges that need to be voided.

## Verify
In each environment, call the payment provider's own "who am I" / account
info endpoint (most providers expose one) using the configured credentials
at deploy time as part of a smoke test, and assert the returned account
mode (test or live) matches the expected mode for that environment before
allowing traffic -- fail the deploy if it doesn't match.
