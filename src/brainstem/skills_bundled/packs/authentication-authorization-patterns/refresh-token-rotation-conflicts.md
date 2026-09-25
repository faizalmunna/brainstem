---
name: refresh-token-rotation-conflicts
description: Refresh token rotation either logs out legitimate users after normal concurrent use or fails to detect a stolen token being replayed.
triggers: ["refresh token reuse detected", "logged out after refreshing on two devices", "refresh token rotation breaking sessions", "stolen refresh token replay", "token reuse error kills session"]
permissions: ["READ"]
---

## Symptom
Two failure modes show up under the same feature -- refresh token rotation -- and get reported as opposite bugs: (a) legitimate users get abruptly logged out with a "refresh token reuse detected" error after ordinary use (multiple tabs, a mobile app and web session simultaneously, or a retried request), or (b) a leaked/stolen refresh token keeps working indefinitely with no alert, meaning rotation isn't actually being enforced. Both trace back to how the "old refresh token was already used" case is detected and handled.

## Likely causes
1. **Rotation is enforced too strictly for legitimate concurrency** -- every refresh invalidates the previous token immediately with no grace window, so two near-simultaneous requests (a race between tabs, or a client retry after a network blip that actually succeeded server-side) both present the same "current" token and the second is treated as reuse of a stolen token.
2. **No reuse detection at all** -- the server rotates the token (issues a new one) but never invalidates the old one, so both the legitimate refresh token and a copy an attacker exfiltrated keep working forever, silently.
3. **Reuse is detected but the response is wrong** -- on detecting reuse, the server should revoke the entire token family (all tokens descended from that chain) to kill a stolen session, but instead just rejects the single request, leaving the attacker's still-valid rotated token usable.
4. **Multiple legitimate devices/sessions share one refresh token chain** instead of each getting its own, so rotating on one device invalidates the token the other device is about to use, causing cross-device logout that looks like reuse.
5. **Client-side race**: the frontend fires two refresh calls in parallel (e.g. two failed requests both trigger refresh) instead of serializing them, so the second call always looks like reuse of an already-rotated token -- a client bug, not a server policy bug.

## Diagnose
- Reproduce the "logged out unexpectedly" report with two browser tabs open to the same account and force both to refresh near-simultaneously (throttle network, or trigger two 401s at once) -- if this reliably reproduces the reuse error, it's a legitimate-concurrency false positive, not an attack.
- Check the refresh endpoint's logic for what happens on detecting an already-used token: does it revoke just that request, or the entire token family (walk the codebase for how token lineage/`family_id` is tracked, if at all)?
- Check whether each login/device issues its own independent refresh token chain, or whether all sessions for a user share one -- inspect the token issuance code and the DB schema for a device/session identifier alongside the refresh token record.
- On the client, check whether concurrent 401s each independently call refresh, or whether they're deduplicated behind a single in-flight refresh promise.
- If reuse is suspected of going undetected, manually replay an old (already-rotated) refresh token against the endpoint after a legitimate rotation and confirm whether the server rejects it or issues valid tokens.

## Fix
Design rotation with three parts working together: (1) each refresh issues a brand-new refresh token and immediately marks the previous one used, scoped per device/session (a `family_id` or session identifier so unrelated sessions don't interfere with each other); (2) on detecting a reuse of an already-used token, revoke the *entire* family, not just the one request, and force re-authentication for that session -- this is what actually protects against a stolen token, since the attacker's and the legitimate user's next refresh will race and whichever loses triggers full revocation; (3) tolerate a short grace window (a few seconds) where the immediately-prior token is still accepted once, to absorb legitimate network retries and near-simultaneous requests, without extending that grace to older tokens further back in the chain. On the client, serialize refresh calls behind a single in-flight lock so concurrent 401s don't generate parallel refresh attempts against the same token.

## Pitfalls
Making the grace window too generous (or permanent) to "fix" the false-logout complaints quietly reopens the replay hole this feature exists to close -- a stolen token would then also enjoy that same grace period. Conversely, revoking only the single offending request on reuse detection (instead of the whole token family) means a detected theft doesn't actually terminate the attacker's access, just makes that one attempt fail -- log the detection but verify the family-revocation code path actually runs, not just the rejection.

## Verify
Simulate concurrent legitimate use (two tabs/devices refreshing within the grace window) and confirm neither is logged out; separately, capture a valid refresh token, use it once normally, then replay the *same* (now-rotated-out) token again and confirm the server revokes the entire session family and that all tokens in that chain -- including the one issued by the legitimate rotation -- are rejected afterward, not just the replayed one.
