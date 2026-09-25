---
name: jwt-algorithm-confusion-attack
description: JWT verification code runs but can still be bypassed because the token's algorithm header is trusted, letting an attacker downgrade to alg none or HMAC.
triggers: ["jwt alg none vulnerability", "rs256 to hs256 confusion", "jwt verification bypass despite checking signature", "alg header attacker controlled", "jwks public key used as hmac secret"]
permissions: ["READ"]
---

## Symptom
Unlike a token that's accepted with no verification at all, here signature verification code genuinely runs and normally works correctly -- but a crafted token with a modified `alg` header in the JWT still gets accepted as valid. Typically found via security testing: sending a token with `"alg": "none"` and an empty signature, or a token signed with HMAC using the server's *public* RSA key as the HMAC secret, gets treated as authentic by an endpoint that "does" verify signatures.

## Likely causes
1. **The verification library is configured to accept whatever algorithm the token itself specifies** (reads `alg` from the token header and uses it to decide how to verify) instead of pinning to one expected algorithm, so an attacker can set `alg: none` and have some libraries skip signature checking entirely.
2. **An RS256-issuing system's verification code accepts HS256 too**, and the same value used as the RSA *public* key (often published, e.g. via a JWKS endpoint) is reused as the HMAC *secret* -- since HMAC verification only needs a symmetric secret to both sign and verify, an attacker who knows the public key can forge a validly-"verified" HS256 token.
3. **The verification call doesn't pass an explicit `algorithms=[...]` allowlist**, relying on library defaults that may be permissive (some JWT libraries historically defaulted to trusting the token's own header if not told otherwise).
4. **Key selection is driven by an attacker-controlled `kid` (key ID) header without validating it against a known set** -- combined with algorithm confusion, an attacker can point `kid` at a key they control, or at a resource they can influence the content of (e.g. a `jku` URL under their control), and pair it with an algorithm that treats that content as a symmetric secret.

## Diagnose
- Locate the JWT verification call and check whether it passes an explicit, hardcoded list of accepted algorithms (e.g. `algorithms=["RS256"]`) or omits that parameter / derives it from the token itself.
- Take a legitimately issued token, decode its header, and craft a modified version with `"alg": "none"` and an empty/removed signature segment; submit it and check whether it's accepted.
- If the system uses RS256, obtain the public key (often published at a `/.well-known/jwks.json` or similar endpoint) and craft a new token with `"alg": "HS256"`, signed using that public key string as the HMAC secret; submit it and check whether it's accepted as valid.
- Check whether the `kid` or `jku` header value from an incoming token is used to fetch or select the verification key without validating it against a fixed, trusted set of known keys.

## Fix
Pin the verification call to one explicit, expected algorithm (or a short fixed allowlist appropriate to your key type -- never mixing symmetric and asymmetric algorithms in the same allowlist), passed as a hardcoded parameter rather than derived from the incoming token's own `alg` header. Select the verification key from a server-controlled, trusted source (a fixed key, or a JWKS fetched from a pinned, hardcoded URL and matched by `kid` against *known* keys only) rather than trusting a `kid`/`jku` value from the token to point at arbitrary key material. Reject any token whose header algorithm doesn't match the expected one before attempting verification at all.

## Pitfalls
Fixing this by blocklisting `"none"` specifically (string-matching the alg header) while still deriving the algorithm from the token for everything else leaves the RS256/HS256 confusion variant wide open -- the real fix is an allowlist of expected algorithms checked against a fixed configuration, not a blocklist of one known-bad value. Upgrading the JWT library alone doesn't help if the application code still passes no `algorithms` parameter or reads `alg` from the token to decide how to call the verifier.

## Verify
Confirm both attack variants are rejected: a token with `alg: none` and an empty signature, and (for RS256 systems) a token re-signed as HS256 using the known public key as the HMAC secret. Both should fail verification with a clear algorithm-mismatch error, and neither should reach any code path that treats the token as authenticated.
