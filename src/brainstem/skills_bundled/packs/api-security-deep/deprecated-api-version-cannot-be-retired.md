---
name: deprecated-api-version-cannot-be-retired
description: An old, less-secure API version can never be shut down because production clients still depend on it and no migration was ever enforced.
triggers: ["can't turn off old API version", "v1 API still has security holes but clients use it", "deprecated endpoint never actually removed", "API version sunset blocked by legacy clients"]
permissions: ["READ"]
---

## Symptom
Security or platform review flags that `/api/v1/*` has weaker authentication, no rate limiting, or a known-fixed vulnerability that was only patched in `/api/v2/*`. The team "deprecated" v1 months or years ago, but it's still live and serving real traffic, because some unknown set of clients (internal services, third-party integrators, an old mobile app version still in app stores) will break the moment it's turned off, and nobody has clear visibility into who those clients are or a credible plan to migrate them.

## Likely causes
1. **Deprecation was announced but never instrumented** -- there's a changelog entry or email saying "v1 is deprecated, please migrate," but no tracking of which clients are still calling it, no sunset date enforcement, and no technical mechanism that makes continuing to use v1 progressively harder.
2. **Breaking changes between versions were large enough that migration requires real client-side engineering work**, and without an external forcing function (a hard sunset date, a security incident), migration is permanently deprioritized against feature work on both sides.
3. **Long-tail clients are unidentifiable or unreachable** -- third-party integrators who received an API key years ago with no contact info on file, or old mobile app versions still installed on users' devices that can't be forced to update.
4. **Internal fear of breaking revenue-generating integrations** means engineering leadership repeatedly delays the sunset date whenever it approaches, and each delay resets the clock on client urgency to migrate, since clients learn the deadline is soft.

## Diagnose
- Pull actual request logs/metrics for the deprecated version over the last 30-90 days: count distinct API keys/client IDs still calling it, and rank by volume -- this turns "we can't turn it off" from a vague fear into a concrete, addressable list.
- For each identified caller, check whether there's a contact (account owner, integration owner, app store listing) and whether a deprecation notice was ever actually delivered to them specifically (not just published in general docs).
- Check whether the deprecated version's responses currently carry any machine-readable deprecation signal (`Deprecation` / `Sunset` HTTP headers per RFC 8594, or a warning field in the response body) -- if not, calling clients have no automated way to detect the risk, which explains low migration urgency.
- Check whether v1 and v2 can run behind the same gateway with request/response translation (a compatibility shim), which would let you retire the insecure backend implementation while keeping the v1 *contract* alive temporarily -- this is often more achievable than forcing every client to change their integration code.

## Fix
Treat version sunset as a project with owners and dates, not a one-time announcement:
- Instrument the deprecated version to emit `Deprecation` and `Sunset` HTTP headers (RFC 8594) with a concrete date, and log every caller's identity so you have an accurate, current list of who still needs to migrate -- reach out directly to the highest-volume callers rather than waiting for docs to be read.
- Where feasible, build a compatibility shim at the gateway/API layer that translates v1 requests into v2 calls under the hood, so you can retire the actual insecure implementation while giving unmigrated clients more runway on the contract they already integrated against.
- Set a hard sunset date and actually enforce it -- gradually degrade the old version first (added latency, rate limiting far below what it used to allow) in the weeks before the hard cutoff, so clients feel pressure to migrate before a full outage, and communicate that this specific date will not move.
- For unreachable long-tail clients (old mobile app versions), coordinate with app stores/force-update mechanisms in the client if you control it, or accept and explicitly document the residual risk with a compensating control (e.g. the shim enforces the v2 security fix even for v1-shaped requests) if you don't.

## Pitfalls
Don't let "we might break someone" become a permanent veto -- an old API version with a known security weakness that stays alive indefinitely is itself an active security exposure, and repeatedly moving the sunset date teaches every remaining client that deadlines are negotiable, which guarantees the tail never shrinks. A sunset date that has been pushed more than once needs an executive decision, not another extension.

## Verify
After implementing the shim/deprecation headers, confirm via request logs that distinct-caller count on the deprecated version is trending down week over week following outreach, and before the final cutover, do a dry-run block (return 410 Gone to a small traffic percentage or in a staging environment) to confirm no still-active, business-critical client breaks unexpectedly.
