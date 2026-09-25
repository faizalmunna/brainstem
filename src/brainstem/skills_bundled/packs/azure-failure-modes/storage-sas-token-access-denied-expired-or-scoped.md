---
name: storage-sas-token-access-denied-expired-or-scoped
description: A request to Azure Blob Storage with a SAS token returns AuthorizationFailure or AuthenticationFailed even though the token was generated correctly.
triggers: ["azure blob sas token access denied", "AuthorizationPermissionMismatch sas", "sas token 403 authenticationfailed", "sas token works locally but not from server"]
permissions: ["READ"]
---

## Symptom
A client presenting a Shared Access Signature (SAS) token to Azure Blob
Storage receives a 403 `AuthorizationFailure`,
`AuthorizationPermissionMismatch`, or `AuthenticationFailed`, even though
the token was generated recently, looks syntactically correct, and worked
when tested from a developer's machine or Storage Explorer.

## Likely causes
1. **The token has actually expired relative to the storage service's
   clock**, and the expiry (`se` parameter) was set too short for the
   actual usage pattern (e.g., a token embedded in an email link or a
   long-running upload that outlives a short-lived token), which is easy
   to misdiagnose as a permissions problem because the error message
   doesn't always distinguish "expired" from "wrong permissions" clearly.
2. **An IP restriction (`sip`/`spr` parameters) on the token scopes it to
   an IP range that doesn't include the client's actual egress IP** --
   common when the token was generated assuming a client's public IP but
   the actual request comes from a server behind NAT, a different egress
   IP than expected (e.g., an Azure service's dynamic outbound IP), or
   through a corporate proxy/VPN that changes the visible source IP.
3. **The signed permissions (`sp`) don't include the operation actually
   being attempted** -- e.g., a read-only (`r`) SAS being used for an
   upload (which needs `w` or `c`), or a container-level SAS missing the
   `l` (list) permission needed by a client that lists blobs before
   reading one.
4. **The SAS was generated with a stored access policy that was later
   modified or deleted**, and because a policy-based SAS derives its
   permissions/expiry from the stored policy at request time (not baked in
   at generation time the way an ad-hoc SAS is), changing or removing the
   policy invalidates every SAS issued against it immediately, even ones
   that look unexpired by their own embedded parameters.
5. **The signing key used no longer matches** -- a user-delegation SAS
   signed with an Entra ID-backed key becomes invalid if the underlying
   role assignment granting the signer permission to generate delegation
   SAS tokens is revoked, or an account-key-based SAS becomes invalid after
   a storage account key rotation/regeneration, since the SAS signature is
   cryptographically tied to the specific key version used to sign it.

## Diagnose
- Decode the SAS query string parameters directly (`se`, `st`, `sp`, `sip`,
  `spr`, `sr`, `ss`) and compare `se` (expiry) against current UTC time,
  not local time, to rule out simple expiry first since it's the cheapest
  check.
- Check the exact error code/message in the response body, not just the
  HTTP status -- `AuthenticationFailed` with `Signature did not match`
  points at key mismatch (rotated key or wrong signing method), while
  `AuthorizationPermissionMismatch` points at insufficient `sp` scope for
  the attempted operation.
- If `sip` is present, determine the actual public egress IP the request
  is coming from (e.g., from the storage account's own diagnostic logs, or
  by having the client report what IP it thinks it's using) and compare
  against the allowed range -- server-side and serverless clients
  frequently egress from IPs the token author didn't anticipate.
- If the SAS references a stored access policy (check for an `si`
  parameter in the URL), retrieve the container's current access policies
  (`az storage container policy list`) and confirm the referenced policy
  still exists with the expected permissions/expiry.
- Check Storage Account > Access Keys to see if a key rotation happened
  around the time failures started, and confirm which key version
  (`key1`/`key2`) was used to sign the specific SAS in question.

## Fix
Generate SAS tokens with expiry windows sized to the realistic duration of
use (including clock skew margin), and prefer short-lived user-delegation
SAS tokens signed with Entra ID credentials over long-lived account-key
SAS tokens, since delegation tokens don't need manual rotation tracking
and can be scoped/revoked via Entra ID role assignments. For IP
restrictions, either omit `sip` unless the client's egress IP is genuinely
static and known, or scope it to the actual observed range (e.g., a NAT
gateway's fixed outbound IP) rather than an assumed developer IP range.
Use stored access policies for tokens that need centralized revocability
(so revoking access doesn't require invalidating individually issued
tokens), and treat modifying a stored policy as an operation that
immediately invalidates all SAS tokens depending on it -- communicate that
before changing one in production.

## Pitfalls
Removing IP restrictions entirely to "make the 403 go away" trades a
debugging inconvenience for a real reduction in token security scope --
if IP restriction was a deliberate control, fix the range instead of
dropping it. Also, regenerating a storage account key to rotate
credentials without checking which SAS tokens were signed against the old
key silently breaks every one of them at once, including tokens embedded
in already-delivered client configuration or emailed links that can't be
easily reissued -- stage key rotation (rotate key2 while key1-signed
tokens are still valid, migrate signers, then rotate key1) instead of
rotating the actively-used key directly.

## Verify
Generate a fresh SAS token with corrected parameters and confirm the
specific operation that was failing (upload, read, list) now succeeds
from the actual client environment (not just from a developer machine) --
the network path matters given IP restriction was a plausible cause.
Check Storage Analytics logs (if enabled) or Azure Monitor resource logs
for the storage account to confirm no further 403s occur for that
container over a representative usage window.
