---
name: concurrent-apply-state-lock-corruption
description: Two engineers or CI jobs run terraform apply at the same time and corrupt or overwrite each other's state because remote locking isn't configured or enforced.
triggers: ["terraform state corrupted after two applies", "concurrent terraform apply", "state file overwritten by another apply", "terraform lock not working", "two people ran terraform apply at once"]
permissions: ["READ"]
---

## Symptom
Two engineers (or two CI pipelines) run `terraform apply` around the same
time against the same state, and afterward the state file is missing
resources one of them created, shows stale attribute values, or Terraform
throws errors about resources that "already exist" on the next apply --
even though no `terraform force-unlock` or manual edit happened.

## Likely causes
1. **The backend doesn't support locking at all** (plain local state
   shared over a network drive, or a backend configured without its
   locking mechanism enabled), so Terraform has no way to serialize
   concurrent writes and simply lets the second `apply`'s state write
   clobber the first's.
2. **Locking is supported by the backend but not actually wired up** --
   e.g. an S3 backend configured without a DynamoDB `dynamodb_table` (or,
   on newer Terraform, without S3-native state locking enabled), so
   `terraform apply` proceeds without ever acquiring a lock, or an
   internal/self-hosted backend where the lock table exists but isn't
   referenced in every workspace's backend config.
3. **CI runs bypass locking by design** -- a pipeline step that calls
   `terraform apply -lock=false` (often added historically to work around
   a stuck lock) or that runs multiple pipelines against the same state
   key without any mutex/concurrency-group setting at the CI level, so
   two pipeline runs race even though the backend itself supports
   locking.
4. **A stale lock was force-removed under pressure**, and immediately
   after, a second apply started because the team assumed "unlocked"
   meant "safe," when in fact the first apply was still mid-write.

## Diagnose
- Check the backend block (`terraform { backend "..." { ... } }` or the
  equivalent HCP Terraform/Terraform Cloud workspace settings) for the
  specific backend in use, and confirm it's one with native locking
  support (S3 with DynamoDB or S3 locking enabled, Azure Blob with lease
  support used correctly, GCS, Terraform Cloud/Enterprise) -- not a local
  or NFS-mounted state file.
- Run `terraform plan` in one terminal and, while it's running, run
  `terraform plan` again in a second terminal against the same state --
  if the second command proceeds immediately instead of returning
  `Error acquiring the state lock`, locking is not functioning.
- Grep CI pipeline definitions for `-lock=false` or `TF_CLI_ARGS` env
  vars that inject it, and check whether the CI system's job
  configuration allows two runs of the same pipeline/stage to execute
  concurrently for the same environment.
- Inspect the state file's `serial` number history (via versioned backend
  storage, e.g. S3 object versions) around the incident window --
  competing writes with out-of-order or skipped serial numbers confirm a
  race rather than a single bad apply.

## Fix
Locking must be enforced at every layer that can write state, not just
assumed from the backend type: configure the backend with its locking
mechanism explicitly (DynamoDB table with the correct primary key for
S3, or rely on Terraform Cloud/Enterprise's built-in locking), remove any
`-lock=false` from CI scripts and developer aliases, and add a
concurrency control at the CI orchestration layer (e.g. a concurrency
group keyed on environment/workspace name) so the platform itself refuses
to start a second apply job for the same state while one is in flight.
Treat "an apply can run concurrently with another apply on the same
state" as a hard invariant to break, not a rare edge case -- the fix is
defense in depth: backend lock + CI-level mutex + no manual
lock-bypassing flags in muscle memory.

## Pitfalls
- Reflexively running `terraform force-unlock` whenever a lock blocks an
  apply, without first confirming the other apply actually crashed
  (versus just being slow), reintroduces exactly this race -- force-unlock
  should be a last resort after confirming via process/CI job status that
  no other apply is genuinely running.
- Adding CI-level concurrency control but leaving `-lock=false` in a
  developer's local wrapper script or shell alias still allows a laptop
  apply to race a CI apply; the fix has to cover every entry point that
  can run `apply`, not just the pipeline.

## Verify
With two terminals, start `terraform apply` in one and, while it's
awaiting confirmation or applying, run `terraform plan` in the second --
confirm it fails fast with `Error acquiring the state lock: ... Lock Info`
instead of proceeding, and that after the first apply finishes the lock
is released and the second command succeeds normally.
