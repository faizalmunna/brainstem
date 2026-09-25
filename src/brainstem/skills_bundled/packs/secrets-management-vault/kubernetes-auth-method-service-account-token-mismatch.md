---
name: kubernetes-auth-method-service-account-token-mismatch
description: A pod authenticating to Vault via the Kubernetes auth method fails because the service account, namespace, or bound role configuration doesn't match what Vault expects.
triggers: ["vault kubernetes auth denied", "vault k8s auth service account mismatch", "pod cannot authenticate to vault", "vault role bound service account error"]
permissions: ["READ"]
---

## Symptom

A pod attempting to authenticate to Vault using the Kubernetes auth
method fails, receiving a permission-denied or authentication-failure
response, despite the pod running with what appears to be the correct
service account in the correct namespace.

## Likely causes

- **The Vault role's `bound_service_account_names` or
  `bound_service_account_namespaces` doesn't match the pod's actual
  service account/namespace** -- a mismatch as simple as a typo, or a
  role configured for a different environment's naming convention than
  where the pod is actually running.
- **Vault's Kubernetes auth method configuration points at the wrong
  Kubernetes API server address or has an outdated CA certificate/JWT
  validation configuration**, especially after a cluster upgrade or
  certificate rotation that Vault's auth method config wasn't updated to
  match.
- **The pod's service account token is a legacy long-lived token when
  Vault's auth method expects a projected, time-bound service account
  token (or vice versa)** -- Kubernetes' service account token model
  changed over versions, and a mismatch between what the pod presents and
  what Vault's configuration expects causes validation failures.
- **Vault's Kubernetes auth method is configured to validate tokens via
  the Kubernetes TokenReview API, but Vault's own service account lacks
  permission to call that API** against the target cluster, causing
  every authentication attempt to fail regardless of the requesting
  pod's own configuration.

## Diagnose

1. Check the specific Vault role's bound service account name(s) and
   namespace(s) against the pod's actual `serviceAccountName` and
   namespace in its pod spec.
2. Check Vault's Kubernetes auth method configuration (`kubernetes_host`,
   CA cert, and token reviewer JWT) for staleness relative to the actual
   cluster's current API server address and certificates.
3. Check the Kubernetes version and service account token type in use
   (legacy vs. projected/bound tokens) against what Vault's auth method
   configuration expects.
4. Check Vault's own service account (the one used for the token reviewer
   JWT) has the necessary RBAC permissions in the target Kubernetes
   cluster to call the TokenReview API.

## Fix

Correct the Vault role's bound service account name/namespace to
exactly match the pod's actual configuration. Update Vault's Kubernetes
auth method configuration (host, CA certificate, reviewer JWT) whenever
the underlying cluster's relevant configuration changes, treating this as
part of any cluster upgrade/certificate rotation checklist rather than an
afterthought discovered when authentication starts failing. Ensure
Vault's token-reviewer service account has and retains the necessary
RBAC permissions in the target cluster.

## Pitfalls

Don't grant Vault's token-reviewer service account overly broad
Kubernetes RBAC permissions beyond what's needed for TokenReview calls,
even to quickly resolve a permission-denied error under time pressure --
scope it to exactly the permission needed. Also don't assume a working
configuration stays working indefinitely across cluster upgrades --
Kubernetes API server addresses, certificates, and token formats can all
change in ways that silently break a previously-functioning Vault
Kubernetes auth integration.

## Verify

From the actual pod (or an equivalent test pod with the same service
account/namespace), perform a real authentication attempt against Vault
and confirm it succeeds and returns a token with the expected policies
attached. Confirm a pod with a genuinely different, unauthorized service
account is still correctly denied, proving the role binding is correctly
scoped rather than accidentally opened too broadly.
