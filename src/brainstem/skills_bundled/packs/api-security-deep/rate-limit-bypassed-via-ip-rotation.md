---
name: rate-limit-bypassed-via-ip-rotation
description: A per-IP rate limit is trivially evaded by rotating source IPs or using a distributed botnet, so abusive traffic keeps hitting the endpoint at full volume.
triggers: ["rate limit not working with rotating IPs", "attacker bypassing rate limit using proxies", "distributed brute force despite IP throttling", "credential stuffing keeps succeeding through rate limiter"]
permissions: ["READ"]
---

## Symptom
The API has a rate limiter keyed on client IP (e.g. 100 req/min per IP), yet abuse continues unabated in logs: login brute-forcing, credential stuffing, or scraping keeps succeeding at high volume, and per-IP request counts in the limiter's own metrics look individually low and "compliant" even during the attack.

## Likely causes
1. **IP is the wrong identity boundary for the abuse pattern.** Botnets, residential proxy networks, and cloud IP pools give an attacker thousands of distinct IPs, each staying well under the per-IP threshold while the aggregate volume against one account or endpoint is enormous.
2. **NAT/CGNAT and corporate egress collapse many real users onto few IPs**, so the limiter is tuned loosely to avoid false positives on legitimate shared-IP traffic -- that same looseness is what the attacker exploits.
3. **The rate limiter trusts a spoofable header** (`X-Forwarded-For`, `X-Real-IP`) for the "true" client IP instead of the actual TCP connection IP, so an attacker sets an arbitrary rotating value in the header and every request appears to come from a fresh IP even from a single machine.
4. **The limit key doesn't include the resource being targeted** (e.g. same global per-IP budget for all endpoints), so credential stuffing against one specific `/login` or password-reset endpoint hides inside the IP's overall allowance.

## Diagnose
- Pull the rate limiter's request log for a known abuse window and count distinct source IPs vs. requests per IP -- if you see thousands of unique IPs each making 1-20 requests against the same account/endpoint, IP-keying is confirmed as the wrong control.
- Check how the limiter derives client IP: grep the middleware/proxy config for `X-Forwarded-For` or `X-Real-IP` usage and confirm whether it validates that the value comes from a trusted upstream proxy hop count, or blindly trusts client-supplied headers.
- Cross-reference attacked usernames/API keys/account IDs against IP diversity: if one account is targeted from hundreds of IPs in a short window, that's the signature of credential stuffing evading per-IP limits.
- Check whether the limit is scoped per-endpoint or globally per-IP -- a global budget masks concentrated abuse of one sensitive endpoint.

## Fix
Key rate limits on the identity that actually matters for the abuse pattern, not just network origin, and layer multiple keys rather than relying on one:
- For authenticated endpoints, rate-limit per-account or per-API-key first (this is what an attacker cannot rotate without also rotating valid credentials, which is the actual bottleneck for credential stuffing).
- For unauthenticated endpoints (login, signup, password reset), rate-limit per-target-identifier (the username/email being attempted) in addition to per-IP, since the attacker controls the IP but the target identifier is fixed.
- Only trust `X-Forwarded-For`/`X-Real-IP` when it comes from a known, trusted reverse proxy hop -- validate the header against your proxy's actual `Forwarded` chain (e.g. take the IP the proxy itself observed, not the last hop the client can forge) or use platform-native mechanisms (Cloudflare's `CF-Connecting-IP` after verifying requests actually traverse Cloudflare).
- Add a secondary, coarser-grained limit (e.g. per-ASN or per-subnet, or global anomaly detection on failed-auth rate) to catch distributed low-and-slow attacks that no single-account or single-IP limit would trigger on.

## Pitfalls
Don't respond by just tightening the per-IP threshold aggressively -- this punishes legitimate users behind shared NAT/CGNAT/corporate proxies (a whole office or campus can share one egress IP) while barely inconveniencing a botnet with thousands of IPs. The fix is changing the identity key, not just lowering the number.

## Verify
Simulate the original abuse pattern in a test environment: send the same request volume against one target account/endpoint from 50+ distinct source IPs (or spoofed `X-Forwarded-For` values) and confirm the per-account/per-key limit now triggers and blocks well before the per-IP limit would have, and confirm legitimate traffic from a shared corporate IP is unaffected.
