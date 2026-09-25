---
name: client-pins-to-version-but-still-breaks-on-server-bugfix
description: A client explicitly pins to a specific API version to avoid breaking changes, but still breaks when the server fixes an internal bug within that same pinned version, revealing the version boundary didn't cover the behavior the client relied on.
triggers: ["pinned version still broke", "bugfix within same version broke client", "version pinning did not prevent breakage", "server fix broke client despite pinned version"]
permissions: ["READ"]
---

## Symptom

A client explicitly requests a specific, pinned API version -- exactly
the practice meant to protect against breaking changes -- but still
breaks when the API provider ships an internal bug fix within that same
version number, because the client had come to rely on the buggy
behavior, and the version boundary was never meant to (and structurally
can't) guarantee protection against behavior the provider itself
considers a bug fix rather than a version-relevant change.

## Likely causes

- **The client's behavior implicitly depended on an actual bug**
  (an edge case handled incorrectly, a race condition producing a
  particular but wrong result) that the provider fixed without realizing
  any client depended on the buggy behavior, since bug fixes are
  conventionally considered non-breaking within a version.
- **No formal contract exists distinguishing "bugs client integrations
  might depend on" from "genuinely internal implementation details safe
  to change freely"**, so the provider's own judgment about what's safe
  to fix without a version bump doesn't necessarily match what clients
  have actually built around.
- **The provider doesn't have visibility into which specific behaviors
  each client integration actually depends on**, making it structurally
  impossible to know in advance whether a given bug fix will break
  someone, short of extensive contract testing against every real
  client's actual usage.
- **The client's own test suite doesn't have contract tests against the
  real API behavior**, so a provider-side change (even one within the
  "same version") isn't caught by the client's own testing before it
  causes a production issue.

## Diagnose

1. Confirm exactly what changed on the provider side (the specific bug
   fix) and exactly what client behavior depended on the previous, buggy
   behavior.
2. Assess whether the provider had any way to know this specific fix
   would affect a real client, or whether it was genuinely
   undiscoverable without contract testing against actual client
   behavior.
3. Check whether the client has any contract/integration tests against
   the real API that could have caught this before it reached
   production.
4. Determine whether this is a one-off unlucky case or whether the
   provider has a pattern of making "bug fix" changes that turn out to
   be breaking for some client fairly often, suggesting a deeper process
   gap.

## Fix

For the immediate issue, work with the API provider to either revert the
specific fix (if feasible and the "bug" the client depended on is
low-stakes) or update the client to work correctly with the fixed
behavior. Establish contract testing between significant clients and the
API provider (a shared, executable contract test suite, similar to
consumer-driven contract testing patterns) so a provider-side change --
even one they consider a safe bug fix -- is verified against real client
expectations before shipping, not just against the provider's own
understanding of the version boundary. For providers with many external
clients where this risk is significant, consider treating any behavior
change (even bug fixes) with more caution -- a period of dual behavior
support, or explicit client outreach before shipping a fix to
long-standing behavior.

## Pitfalls

Don't conclude from this incident that version pinning is useless and
abandon the practice -- pinning still protects against the vast majority
of intentional breaking changes; this specific failure mode (depending on
an actual bug) is a narrower, harder problem that contract testing
addresses more directly than version pinning ever could.

## Verify

Confirm the client works correctly against the provider's current
(fixed) behavior after remediation. If contract testing was adopted,
confirm it would have caught this specific incident by running it
against a reproduction of the original bug fix in a test environment.
