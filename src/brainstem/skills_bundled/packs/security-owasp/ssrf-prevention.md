---
name: ssrf-prevention
description: Diagnose Server-Side Request Forgery -- a server-side feature that fetches a user-supplied URL being abused to reach internal-only services or cloud metadata endpoints.
triggers: ["ssrf", "server side request forgery", "fetch url user input", "webhook url validation", "cloud metadata endpoint exposed", "internal service reachable via url fetch"]
permissions: ["READ"]
---

## Symptom
A server-side feature that fetches a URL on the user's behalf (a webhook
registration, an image-fetch-from-URL feature, a PDF-generation-from-URL
tool, a URL preview/unfurl feature) can be pointed at an internal-only
address instead of a legitimate external one -- reaching internal
services not meant to be internet-reachable, or a cloud provider's
instance-metadata endpoint (a classic SSRF target for stealing cloud
credentials).

## Likely causes
1. **No validation at all on the destination of a server-initiated
   fetch** -- the feature accepts any URL and fetches it, trusting that
   users will only ever supply legitimate external URLs.
2. **Validation checks the URL string but not where it actually
   resolves** -- a hostname allowlist/blocklist checked at request time,
   but DNS resolution happening separately at fetch time can point
   somewhere different (DNS rebinding), or a URL can encode an internal
   IP in a form the string check didn't recognize (decimal/octal IP
   notation, IPv6 forms of internal addresses).
3. **Redirects followed automatically** -- an initial URL passes
   validation (a legitimate external domain), but that server responds
   with a redirect to an internal address, which the fetching code
   follows without re-validating.
4. **Cloud metadata endpoints** (a well-known internal-only address
   cloud providers expose for instance credentials/configuration) reached
   via SSRF because the fetching code has no concept of "this address
   range should never be reachable regardless of what validation the URL
   string passed."

## Diagnose
- Identify every feature that performs a server-side fetch based on
  user-supplied input (webhooks, URL previews, "import from URL,"
  document/image fetching, PDF rendering of remote content).
- Check what validation exists: is it purely on the URL string, or does
  it also validate the resolved IP address at actual connection time?
- Check whether redirects are followed, and if so, whether the redirect
  target is re-validated with the same rigor as the original URL.
- Check whether the cloud metadata address range (and other well-known
  internal ranges) is explicitly blocked, or only implicitly excluded by
  a generic "looks like a public URL" check that might not actually
  cover it.

## Fix
- Validate the *resolved* destination at actual connection time, not just
  the URL string at request time -- resolve the hostname, check the
  resulting IP against a blocklist of private/internal/link-local/
  metadata address ranges, and re-check on every redirect hop rather than
  trusting the fetch library to only redirect somewhere safe.
- Explicitly block private IP ranges (RFC 1918), loopback, link-local
  (including the specific cloud-metadata address), and IPv6 equivalents
  -- as a network-layer or fetch-layer control, not just a string-pattern
  check on the input.
- Either disable automatic redirect-following for these fetches, or
  re-validate the destination after each redirect before following it.
- Where feasible, route these fetches through a dedicated, network-
  isolated proxy/service that has no network path to internal
  infrastructure at all, so even a bypass of application-level validation
  can't reach anything sensitive.

## Pitfalls
- A hostname-string-based allowlist/blocklist alone is insufficient
  because DNS resolution isn't fixed at validation time -- an attacker
  who controls DNS for a domain that initially passed validation can
  repoint it to an internal address later (DNS rebinding); validate the
  resolved IP at actual fetch time.
- Blocking only the obvious `169.254.169.254` metadata address without
  blocking the broader private/link-local ranges misses other internal
  targets and IPv6 equivalents.
- Network-layer isolation (the fetching service genuinely has no route to
  internal infrastructure) is a stronger control than application-level
  validation alone, since it doesn't depend on catching every possible
  encoding/redirect trick in code.

## Verify
Attempt to point the feature at a known-internal address (a private IP,
`localhost`, the cloud metadata address if applicable) both directly and
via a redirect from an initially-valid external URL, and confirm both
are rejected -- not just the direct case.
