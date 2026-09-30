---
name: secret-injected-as-plaintext-env-var-visible
description: A secret fetched from Vault is injected into a process as a plaintext environment variable, making it readable by anything with process inspection access on the host.
triggers: ["secret visible in process environment", "vault secret exposed as env var", "credential readable via proc environ", "secret leaked through environment variable"]
permissions: ["READ"]
---

## Symptom

A security review or a specific investigation (e.g. after a container
escape or a compromised sidecar) finds that a secret fetched from Vault
is present in plaintext as an environment variable of a running process
-- readable by anything with sufficient access to inspect that process's
environment (`/proc/<pid>/environ` on Linux, container inspection
commands, a crash dump that includes environment variables).

## Likely causes

- **A common integration pattern injects Vault secrets as environment
  variables at container/process startup** (via an init container, an
  entrypoint script, or a Vault Agent template) for simplicity, without
  considering that environment variables are broadly readable by anyone
  with process-inspection access, are often included in crash dumps and
  debugging output, and can leak into child processes or logging
  frameworks that dump the environment for diagnostics.
- **Logging or error-reporting tooling dumps the full process environment
  on an unhandled exception or as part of diagnostic output**, inadvertently
  capturing and persisting the secret value in log storage.
- **A container orchestration platform's UI or API exposes environment
  variables for debugging purposes** to a broader set of users (anyone
  who can view pod details) than should have access to the actual secret
  value.
- **Child processes spawned by the application inherit the full
  environment by default**, propagating the secret to processes that
  don't actually need it and increasing the surface area where it could
  leak (a subprocess that itself logs its environment, for instance).

## Diagnose

1. Inventory how secrets currently reach the application process --
   environment variables, mounted files, or a runtime API call to
   Vault -- across all services, not just the one under review.
2. Check logging/error-reporting configuration for whether it captures
   and persists the full process environment on errors, and check
   existing log storage for whether any secret values have already been
   captured this way.
3. Check the container orchestration platform's access controls for who
   can view pod/container environment variable details, and compare
   against who should be able to see actual secret values.
4. Check whether child processes spawned by the application need the
   secret at all, or whether they're inheriting it unnecessarily via
   default environment inheritance.

## Fix

Prefer injecting secrets via mounted files (a tmpfs-backed volume, Vault
Agent's file-templating feature) rather than environment variables --
file-based secrets aren't captured by generic "dump the environment"
diagnostic patterns and can have filesystem permissions restricting
access more precisely than process-environment visibility allows. Where
environment variables are unavoidable (some tools/frameworks only support
that pattern), explicitly configure logging/error-reporting tools to
scrub or exclude sensitive environment variable names from any captured
diagnostic output. Restrict child process environment inheritance to only
what's actually needed rather than passing the full environment by
default. Restrict who can view pod/container details in the orchestration
platform's UI/API to those who genuinely need that access.

## Pitfalls

Don't treat this as solved by simply renaming the environment variable to
something less obviously secret-looking -- that's obscurity, not a real
control; the fix is changing the delivery mechanism (files instead of
env vars) or genuinely restricting access to environment inspection, not
disguising the variable name. Also, if a secret has already been
captured in a log or crash dump due to this pattern, treat that as an
actual exposure requiring rotation, not just a logging configuration fix
going forward.

## Verify

After switching to file-based secret injection, confirm the secret no
longer appears in `/proc/<pid>/environ` or equivalent process-environment
inspection for the running container/process. Trigger the previously
environment-dumping error/logging path deliberately in a test environment
and confirm the secret value no longer appears in the resulting log
output.
