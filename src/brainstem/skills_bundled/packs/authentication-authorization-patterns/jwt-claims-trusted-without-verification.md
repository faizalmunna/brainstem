---
name: jwt-claims-trusted-without-verification
description: An API accepts a JWT's claims as authoritative without actually verifying its signature, issuer, or audience, letting a forged token impersonate any user.
triggers: ["jwt decoded but not verified", "forged jwt accepted", "anyone can impersonate user with fake token", "jwt.decode without verify", "token accepted from wrong issuer"]
permissions: ["READ"]
---

## Symptom
A security review or pen test (or an incident) finds that the API will accept a JWT whose payload has been tampered with -- a different `sub`/user ID, an added `role: admin` claim, or a token issued for a completely different application -- as long as it's structurally a valid-looking JWT. In code, this usually traces to a call like `jwt.decode(token, verify=False)` or a manual base64-decode of the payload, used somewhere in the request path to read claims without the corresponding verification step ever running.

## Likely causes
1. **Decoding used for convenience without verification** -- a developer needed to read a claim (e.g. to log the user ID) and reached for a "decode" function that, in most JWT libraries, does not verify the signature by default or when passed `verify_signature=False`/no key, and that unverified decode result got reused downstream as if it were trusted.
2. **Signature verified, but issuer (`iss`) not checked** -- the app validates against a public key, but if that key is fetched dynamically per-token (e.g. via a JWKS URL taken from the token itself, or a multi-tenant IdP setup), a token from a *different*, attacker-controlled issuer that happens to sign correctly with its own key still passes.
3. **Signature verified, but audience (`aud`) not checked** -- a token legitimately issued by the correct IdP for a *different* application (e.g. a mobile app's token, or a partner integration's token) is accepted by this API because nothing confirms the token was meant for this API specifically.
4. **Verification happens in one code path but not another** -- middleware verifies tokens for most routes, but a specific handler, background job, or internal service-to-service call reads and trusts a JWT independently, bypassing the shared verification logic.
5. **Verification key/algorithm not pinned**, allowing an attacker to influence which key or algorithm is used to check the signature (a related but distinct issue from outright skipping verification -- see the algorithm-confusion skill in this pack for that specific case).

## Diagnose
- Grep the codebase for JWT decode calls (`jwt.decode`, `jwt_decode`, `jose.jwt`, manual `atob`/base64 splitting of the token) and check each call site: does it pass a verification key and require signature checking, or does it decode without verifying?
- For each verified call site, check whether `issuer` and `audience` parameters are explicitly passed and enforced by the library (many libraries verify the signature by default but only check `iss`/`aud` if you explicitly ask them to).
- Craft a test JWT with an altered payload (different `sub`, added privileged claim) signed with an arbitrary key (or `alg: none` if supported) and send it to each authenticated endpoint; note which ones accept it.
- Check for any endpoint, admin tool, or background worker that reads claims from a token passed through headers/query params without going through the same central auth middleware as the main request path.

## Fix
Route every place that reads JWT claims through a single, shared verification function that validates the signature against the correct key (fetched from a trusted, pinned source -- not derived from attacker-controlled input like a `kid` pointing at an arbitrary URL), and explicitly checks `iss` matches the expected issuer and `aud` matches this specific API/application, rejecting the token otherwise. Never use an unverified "decode for convenience" call in any code path that influences authorization or trust decisions -- if a claim is needed before full verification (e.g. to pick which key to verify with, such as reading `kid`), treat that pre-verification read as untrusted and only use it to *select* the verification key, never to make any decision about the request.

## Pitfalls
A common half-fix is verifying the signature but forgetting `iss`/`aud`, which still leaves cross-issuer or cross-application token confusion open -- a token from a legitimate but different source can still pass. Another is verifying correctly in the main HTTP middleware but leaving an older or "internal" code path (a debug endpoint, an internal microservice call, a WebSocket auth handshake) using the old unverified decode, because it was written before the shared verifier existed and never migrated.

## Verify
Send a JWT with a valid structure but an invalid signature (flip one character in the signature segment) to every authenticated endpoint and confirm all reject it with 401; separately, send a token that's validly signed by the correct key but has the wrong `aud` or `iss` claim and confirm it's also rejected, not just signature-checked.
