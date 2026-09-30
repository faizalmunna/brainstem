---
name: plaintext-secrets-committed-in-values-files
description: Real credential values like API keys or database passwords are committed directly in a chart's values.yaml or a per-environment values file.
triggers: ["secret committed in values.yaml", "api key in values file git", "helm values file has plaintext password", "should not commit secrets helm chart", "values-prod.yaml has real credentials"]
permissions: ["READ"]
---

## Symptom
A `values-prod.yaml` (or similar per-environment file) in the chart's
repository contains an actual, working credential -- a database
password, an API key, a TLS private key -- in plaintext, not a
placeholder or a reference. This is often discovered during a security
review, an audit, or after the fact when a credential is found working
against production despite "being in git," which nobody treated as a
live secret at the time it was added.

## Likely causes
1. **No externalized secrets mechanism was ever set up**, so the
   fastest path to "make the chart work with real credentials" during
   initial setup was pasting the value directly into the values file
   that already existed for everything else -- there was no friction or
   established alternative pattern pointing toward a secrets manager
   instead.
2. **A `Secret` template in the chart reads directly from
   `.Values.someSecret`**, which makes the values file the *only* input
   mechanism the chart supports for that field -- even a security-aware
   engineer has no better option without changing the chart itself to
   support an external reference.
3. **Per-environment values files are treated as equivalent to
   environment variables/local config** rather than as version-controlled,
   permanently-retained artifacts -- the mental model "this is just
   config, not code" obscures that git history keeps every value
   forever, unlike a `.env` file that might be gitignored.
4. **A values file was marked `.gitignore`d for production but a
   different, lower-environment file with the same real credential
   (reused across environments) wasn't**, so the secret still ends up
   committed via the environment where discipline was lower, defeating
   the protection applied elsewhere.

## Diagnose
- Search git history (not just the current working tree) for credential
  patterns across all values files: `git log --all -p -- '*values*.yaml'
  | grep -iE 'password|secret|token|api[_-]?key|-----BEGIN'` -- a value
  removed from the current file is still present in history unless
  history itself was rewritten.
- Grep current chart templates for any `Secret` resource that sources
  its `data`/`stringData` directly from `.Values.x` rather than from an
  external reference (`valueFrom`, an operator-managed source, a
  pre-existing Secret name) -- this identifies which fields structurally
  have no alternative to plaintext values today.
- Check whether the same credential value appears across multiple
  environment files (dev/staging/prod sharing one password) -- this both
  indicates weak secret hygiene independent of the git-commit issue and
  means a single leak compromises every environment at once.
- Confirm whether any external secrets tooling (Sealed Secrets, External
  Secrets Operator, Vault, cloud-provider secret manager) is already in
  use ANYWHERE in the org's other charts/repos -- reinventing the pattern
  from scratch is unnecessary if one is already standardized elsewhere.

## Fix
- Rotate every discovered credential immediately -- removing it from the
  current file does not invalidate it, and it remains readable by
  anyone with repository access via git history indefinitely until
  rotated at the source system.
- Restructure the chart's Secret template to source values from an
  external mechanism rather than raw `.Values`: either integrate the
  External Secrets Operator (chart references an `ExternalSecret` object
  pointing at a cloud/Vault secret path, and only a non-sensitive
  reference/path lives in values.yaml), or use Sealed Secrets (values
  file holds an encrypted blob that's useless without the cluster's
  private key, safe to commit).
- For values files that must reference *some* secret identifier, keep
  only non-sensitive references there (a secret name, an ARN, a Vault
  path) and never the value itself -- audit the chart's
  `values.schema.json`/documentation to make clear which fields are
  references vs. which (if any legitimately remain) are raw values.
- Purge the credential from git history if the repository's exposure
  window and access scope make that worthwhile (`git filter-repo` or
  equivalent), understanding this is defense-in-depth after rotation,
  not a substitute for it -- rotation is the step that actually
  invalidates the leaked value.

## Pitfalls
- Rewriting git history to remove a secret without rotating it first
  provides false reassurance -- anyone who already cloned the repo, or
  any CI cache/artifact that captured the file, still has the old,
  still-valid credential.
- Moving secrets to an external manager but leaving the chart's
  `values.schema.json`/README undocumented about the new expected
  reference format leads engineers to reflexively paste a raw value back
  into values.yaml the next time a new credential is needed, silently
  reintroducing the same problem in a chart that "already fixed" it.

## Verify
Run the git-history secret-pattern grep again after remediation and
confirm no plaintext credential remains reachable in any historical
commit for values files still in active use, and confirm the rotated
credential's old value no longer authenticates against the live system
(a deliberate failed-auth test against the old value, not just
inference).
