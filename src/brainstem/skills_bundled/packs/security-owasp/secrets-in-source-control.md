---
name: secrets-in-source-control
description: Respond correctly to a secret (API key, password, token) committed to git -- rotation, not just deletion, and understand why removing the file isn't enough.
triggers: ["leaked secret git", "api key committed", "secret in git history", "accidentally committed password", "credentials in repo", "leaked api key"]
permissions: ["READ", "SECRET"]
---

## Symptom
A secret (API key, database password, private key, auth token) is found
committed to a git repository -- either in the current working tree or
buried in history from a past commit -- and the immediate instinct is to
delete the file and commit that deletion.

## Likely causes
1. **A `.env` file or config with real credentials committed directly**
   instead of a `.env.example` template, often because `.gitignore`
   didn't include it from the start or was added too late (after the
   first commit already happened).
2. **A secret hardcoded in source** (a connection string, an API key
   constant) during initial development "temporarily," never moved to
   environment variables/a secrets manager before merging.
3. **A secret present in an old commit that was later "removed"** by
   deleting the file in a subsequent commit -- the file is gone from the
   current working tree, but the secret is still fully present and
   retrievable in git history.
4. **A secret leaked via a CI log, an error message, or a debug print**
   that got committed as part of a log file or fixture, not the "obvious"
   places (config files) that get checked first.

## Diagnose
- Confirm exactly what's exposed: which secret, what it grants access to,
  and how long it's been in the repository (check the commit history for
  when it was first introduced, and whether the repo is/was public or
  had broader internal access than the credential should have had).
- Search git history specifically, not just the current tree
  (`git log -p` for the relevant file, or a secret-scanning tool run
  against full history) -- a secret "removed" in a later commit is still
  present in every commit before that one.
- Check whether the secret shows any sign of unauthorized use (unexpected
  API usage, unfamiliar login locations, unexpected charges) to gauge
  whether this is a hygiene issue or an active incident.

## Fix
- **Rotate the credential first, immediately** -- generate a new key/
  password/token and revoke the old one at the provider -- before doing
  anything else. This is the step that actually neutralizes the exposure;
  everything else is cleanup.
- Only after rotation, remove the secret from the current working tree
  and, if it's a real ongoing risk (public repo, broad access, sensitive
  scope), rewrite git history to purge it (tools like `git filter-repo`)
  -- understanding this rewrites history and requires coordinating with
  anyone else who has clones of the repo, since their local history will
  diverge.
- Move the credential to environment variables or a proper secrets
  manager, with `.env`/equivalent added to `.gitignore` *before* any real
  value is ever written to it, and a `.env.example` with placeholder
  values committed instead.
- Add a secret-scanning pre-commit hook or CI check going forward so a
  future accidental commit is caught before it merges, not after.

## Pitfalls
- **Deleting the file without rotating the credential first** leaves the
  actual exposure fully live -- the secret is still valid and still
  present in git history; a "fix" that's just a follow-up commit removing
  the file gives false confidence while doing nothing to stop misuse.
- Rewriting git history without rotating the credential first, then
  rotating later, still leaves a window where the old (still-valid at the
  time) secret was fully exposed in history before the rewrite -- order
  matters: rotate, then clean up history, not the reverse.
- Rewriting history on a shared repository without coordinating force-
  pushes and re-clones with the team can silently reintroduce the secret
  if someone pushes from an un-rebased local clone afterward.

## Verify
Confirm the old credential is actually revoked (attempt to use it and
confirm it fails) and the new one works in its place; if history was
rewritten, confirm via a fresh clone (not a previously-existing local
clone) that the secret no longer appears anywhere in the repository's
history.
