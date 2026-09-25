---
name: state-file-plaintext-secrets-exposure
description: The Terraform state file contains database passwords, API keys, or other secrets in plaintext and is readable by anyone with access to the state backend.
triggers: ["terraform state has secrets in plaintext", "sensitive value in terraform state", "who can read terraform state file", "terraform state security audit", "secrets exposed in state file"]
permissions: ["READ"]
---

## Symptom
A security review, audit, or incident finds that the Terraform state
file -- in S3, Terraform Cloud, GCS, or wherever the backend stores it --
contains plaintext secrets (a generated database password, an API key
returned by a provider, a TLS private key) even though the corresponding
`.tf` files never hard-code the value, and anyone with read access to the
state storage (which is often a broader group than "people who can run
`terraform apply`") can read them.

## Likely causes
1. **Terraform state stores the full resource attribute set by design**,
   including any attribute marked `sensitive` in a variable or output --
   `sensitive = true` only suppresses the value from CLI output and logs,
   it does not encrypt or omit it from the state file itself, which is a
   common and dangerous misunderstanding.
2. **A resource generates or returns a secret as a computed attribute**
   (e.g. a `random_password` resource, or a cloud resource whose create
   response includes an initial credential), and that value is stored in
   state as plaintext regardless of how it's referenced in code.
3. **The state backend itself isn't encrypted at rest or has overly broad
   access controls** -- an S3 bucket without default encryption and with
   a bucket policy granting read to a wide IAM group/role, or a
   Terraform Cloud workspace where more team members have read access
   than actually need it.
4. **Secrets were passed into Terraform as plain variables** (e.g. a
   `tfvars` file or `TF_VAR_` environment variable containing a real
   secret) instead of being fetched from a secrets manager at apply time,
   so the secret entered Terraform's data flow at the earliest possible
   point and ends up in both state and (if not gitignored) version
   control.

## Diagnose
- Run `terraform show -json | grep -i` (or a proper JSON query with
  `jq`) for likely secret field names (`password`, `secret`, `key`,
  `token`, `credential`) across the state to confirm which specific
  resources/attributes are exposing plaintext values, rather than
  assuming the scope of exposure.
- Check the backend's access controls directly: for S3, review the
  bucket policy and any IAM policies granting `s3:GetObject` on the state
  key; for Terraform Cloud/Enterprise, review workspace team access
  levels; confirm the *actual* set of principals who can read state,
  which is frequently larger than the set who run applies.
- Confirm whether backend encryption at rest is enabled (S3 default
  encryption/SSE, GCS default encryption, Azure Storage encryption) --
  encryption at rest doesn't stop a legitimate reader from seeing
  plaintext, but its absence is a compounding risk if the storage itself
  is ever exfiltrated.
- Search version control history and CI logs for the same secret values
  found in state, to determine whether the exposure is confined to the
  state backend or has already leaked further (git history, CI log
  output, artifact storage).

## Fix
Assume Terraform state must be treated as a secrets store and controlled
accordingly: restrict read access to the state backend to the minimum
set of principals/roles that genuinely need it (separate from who can
plan/apply, where feasible, via backend-specific access controls),
ensure the backend enforces encryption at rest and in transit, and for
secrets Terraform must generate or handle, prefer resources/providers
that integrate with a secrets manager (writing the generated value
directly into Vault/AWS Secrets Manager/etc. via a provider resource)
over storing the raw value as a plain Terraform attribute wherever the
provider supports it. For secrets that must exist as state attributes
regardless (many provider schemas leave no alternative), treat any
already-exposed secret as compromised once broader-than-intended access
is discovered -- rotate it -- rather than treating access-control
tightening alone as remediation.

## Pitfalls
- Believing `sensitive = true` on a variable or output solves the
  problem -- it only redacts the value from `plan`/`apply` console output
  and the CLI's `-json` summaries in some cases; the raw value is still
  written to the state file in full.
- Rotating the exposed secret without also fixing the underlying access
  control or data-flow issue means the next generated secret (e.g. on the
  next `random_password` regeneration or resource recreation) lands in
  state with the same exposure, recreating the identical problem.

## Verify
After tightening access controls and rotating any already-exposed
secrets, re-run the same targeted search against the current state
(`terraform show -json` piped through a search for secret-like field
names) to confirm no plaintext secret remains reachable by a broader
audience than intended, and confirm via the backend's access-control
listing (IAM policy simulator for S3, team access page for Terraform
Cloud) that only the intended principals can read the state object.
