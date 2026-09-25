---
name: dynamic-secret-lease-expires-mid-operation
description: An application using a Vault-issued dynamic database credential starts failing authentication mid-operation because the credential's lease expired before it was renewed or replaced.
triggers: ["vault dynamic secret expired", "database credential lease expired", "vault lease renewal not working", "dynamic secret authentication failure mid-request"]
permissions: ["READ"]
---

## Symptom

An application using Vault's dynamic secrets engine (issuing short-lived
database credentials, cloud provider credentials, etc.) starts failing
authentication against the backing system partway through normal
operation, despite having successfully authenticated with the same
credential shortly before -- the credential simply stopped working
without any application-level change.

## Likely causes

- **The application fetched a dynamic credential once at startup and
  never renews or re-fetches it**, treating it like a static, permanent
  credential, so it inevitably fails once the lease's TTL expires.
- **Lease renewal logic exists but doesn't handle the renewal request
  failing** (network blip, Vault temporarily unavailable), silently
  leaving the application to keep using a credential that's about to (or
  already did) expire.
- **The lease's maximum TTL was reached** -- Vault leases typically have
  both a TTL and a max TTL; even with correct periodic renewal, a lease
  can't be renewed past its max TTL and needs a fresh credential issued
  instead of a renewal at that point.
- **A long-lived connection pool holds connections established with an
  old credential** -- even after the application correctly fetches a new
  credential, previously-established database connections using the old
  one may still be in the pool and fail once the old credential is
  actually revoked/expired on the database side.

## Diagnose

1. Check the application's credential-fetching code for whether it
   implements lease renewal/refresh at all, or fetches once and reuses
   indefinitely.
2. Check Vault's audit log or the specific secret engine's lease
   information for the actual TTL and max TTL configured, and compare
   against how long the application actually ran before failing.
3. Check for renewal-related errors in application logs around the time
   of failure -- a failed renewal attempt that wasn't handled/retried
   would show up here if renewal logic exists but isn't robust.
4. For connection-pool-related failures, check whether the pool's
   connections were established before or after the most recent
   credential refresh, and whether the pool proactively cycles
   connections tied to an old credential.

## Fix

Implement proper lease renewal using Vault's renewal API well before the
lease's TTL expires, with retry/backoff for renewal failures, and fall
back to fetching an entirely new credential when a lease can't be
renewed further (approaching or at its max TTL). For connection pools,
ensure the pool is aware of credential rotation and proactively
recycles/re-establishes connections using the current credential rather
than holding onto connections tied to a credential that's about to
expire. Consider using a Vault-aware client library or sidecar (Vault
Agent, or a language-specific Vault SDK with built-in lease management)
rather than hand-rolling renewal logic, since correct lease lifecycle
handling has enough edge cases to be worth not reimplementing per
application.

## Pitfalls

Don't respond to lease expiration issues by setting an extremely long
TTL to avoid dealing with renewal -- that undermines the core security
benefit of dynamic, short-lived credentials (limiting the blast radius
of a leaked credential); fix the renewal logic instead of avoiding the
short lease. Also don't assume a successful renewal API call means the
credential is immediately usable everywhere -- connection pools and
cached credentials elsewhere in the application still need their own
refresh logic.

## Verify

Deliberately let a lease approach expiration in a test environment and
confirm the application correctly renews it (or fetches a fresh
credential) before failure, with authentication continuing to succeed
across the renewal boundary. Test the failure path too -- simulate a
renewal request failing and confirm the application retries rather than
silently continuing to use a soon-to-expire credential.
