---
name: key-vault-managed-identity-access-denied-model-mismatch
description: A managed identity granted permission to a Key Vault still receives 403 Forbidden because of RBAC/access-policy model mixing or role propagation delay.
triggers: ["key vault forbidden managed identity has permission", "keyvault access denied after granting role", "vault access policy vs rbac permission model", "key vault 403 caller is not authorized"]
permissions: ["READ"]
---

## Symptom
A managed identity (system-assigned or user-assigned) has been granted
access to a Key Vault -- either via an access policy or an RBAC role
assignment -- but calls to retrieve a secret/key/certificate still fail
with `403 Forbidden`, `Caller is not authorized to perform action`, or
`Access denied`, even though the Azure portal appears to confirm the
grant is in place.

## Likely causes
1. **The Key Vault's permission model is Azure RBAC, but the grant was
   made as a vault access policy (or vice versa)** -- a Key Vault has a
   single `enableRbacAuthorization` setting that determines which
   authorization system is actually consulted; if it's set to use Azure
   RBAC, legacy access policies are ignored entirely regardless of how
   correctly they were configured, and the reverse is equally true.
2. **The role assignment was made at the wrong scope** -- e.g., assigned
   at the subscription or resource group level expecting it to cascade,
   but a more specific deny-by-omission expectation, or assigned to the
   vault resource but the identity actually needs data-plane access which
   requires a specific role like `Key Vault Secrets User`, not a
   management-plane role like `Key Vault Contributor` (which grants
   control over the vault resource itself but not read access to secret
   values).
3. **RBAC role assignment propagation delay** -- Azure RBAC assignments
   can take up to several minutes to take effect across all Key Vault data
   plane endpoints, so an identity tested immediately after a role grant
   can genuinely be denied for a transient window even though the
   assignment is correctly configured.
4. **The identity used at runtime isn't the one that was granted access**
   -- a common mismatch is granting the system-assigned identity of one
   resource while the application code actually authenticates using a
   different user-assigned managed identity attached to the same resource,
   or `DefaultAzureCredential` falling back to a different credential
   source (e.g., a developer's `az login` session) in local testing versus
   the actual managed identity in production, masking which identity is
   really being evaluated.
5. **Key Vault firewall/network rules block the request independent of
   RBAC**, so even a correctly authorized identity gets denied if the
   vault's network ACLs don't allow the calling resource's network path
   (missing "Allow trusted Microsoft services" exception, or the calling
   resource isn't on an allowed VNet/private endpoint) -- this produces a
   network-layer denial that can be misread as an authorization problem.

## Diagnose
- Check `az keyvault show --name <vault> --query
  properties.enableRbacAuthorization` to determine definitively which
  model is active, then verify the grant was made using the matching
  model (RBAC role assignment vs. `az keyvault set-policy`) -- don't trust
  portal blade appearance alone, since both blades can be visible even
  when one is inert.
- If RBAC is active, run `az role assignment list --assignee
  <identity-object-id> --scope <keyvault-resource-id>` and confirm both
  the specific role (e.g., `Key Vault Secrets User` for read, not a
  management-plane role) and that the scope covers the vault being
  called.
- Check Key Vault's diagnostic logs (`AuditEvent` category, if diagnostic
  settings are configured to Log Analytics) for the actual denied request
  -- it shows the exact identity object ID that was evaluated and denied,
  which confirms or rules out an identity mismatch immediately.
- Confirm which credential is actually active at runtime by logging the
  identity claims from the token `DefaultAzureCredential` (or the SDK's
  equivalent) acquires, rather than assuming the intended managed identity
  is the one being used.
- Check Key Vault's Networking blade for firewall rules and confirm
  whether "Allow trusted Microsoft services to bypass this firewall" is
  enabled if the caller is an Azure service, or that a private endpoint
  exists on the calling resource's VNet if public network access is
  disabled.

## Fix
Standardize on Azure RBAC for the Key Vault's authorization model (the
Microsoft-recommended direction over legacy access policies) and remove
any leftover access policies so there's no ambiguity about which system
governs access. Grant the specific least-privilege data-plane role needed
(`Key Vault Secrets User`/`Key Vault Certificate User`/`Key Vault Crypto
User` for read/use operations, reserving `Key Vault Administrator` for
actual management) scoped to the vault or a narrower resource group,
rather than a broad management-plane role assumed to imply data access.
Confirm at code level exactly which managed identity is used at runtime
(explicit client ID for user-assigned identities rather than relying on
ambient default resolution) so the identity granted access and the
identity making the call are provably the same. Build in a short retry
with backoff for the first call after a fresh role assignment to absorb
propagation delay in automated deployment pipelines.

## Pitfalls
Mixing both models "just in case" (leaving access policies in place while
also using RBAC) creates confusion about which grant is actually
authoritative and makes future audits unreliable, since a reviewer can see
an access policy that looks permissive but is entirely inert under RBAC
mode. Also, granting `Key Vault Administrator` or Owner-level roles to
unblock a stuck deployment, instead of diagnosing the actual scope/role
mismatch, leaves a much broader permission in place than the workload
needs and is easy to forget to narrow later.

## Verify
After correcting the model/role/scope, wait a few minutes for propagation
and re-run the exact failing operation (retrieve the specific
secret/key/certificate) using the actual production identity, not a
developer's local credential. Confirm via Key Vault diagnostic logs that
the request now shows as authorized for that identity's object ID. Run
`az role assignment list` once more to leave a clean record of exactly one
authoritative grant per identity, with no orphaned access policies
remaining if RBAC is the chosen model.
