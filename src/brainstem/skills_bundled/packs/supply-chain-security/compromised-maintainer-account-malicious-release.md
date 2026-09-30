---
name: compromised-maintainer-account-malicious-release
description: A trusted, long-used package suddenly ships a new version with obfuscated code or unexpected network calls after its maintainer's publish credentials were compromised.
triggers: ["package we've used for years suddenly acting weird after update", "new version of trusted package has obfuscated code", "npm package publishing suspicious network requests", "maintainer account hijacked malicious release", "loose version constraint pulled in a bad update overnight"]
permissions: ["READ"]
---

## Symptom
A package that has been a stable, trusted dependency for a long time (high
download counts, years of clean history) publishes a new version, and
shortly after, builds or running applications that pulled it in via a
loose version constraint (`^`, `~`, or unpinned) start exhibiting unexplained
behavior: unexpected outbound network calls, crypto-mining CPU spikes,
credential-looking data appearing in logs sent somewhere unexpected, or a
security scanner/EDR flags obfuscated code in a file that previously had
none. Nothing in the application's own code changed.

## Likely causes
1. **The package maintainer's publish credentials (npm/PyPI account, 2FA-
   less API token) were phished or leaked**, and the attacker published a
   malicious version under the legitimate package name -- this is
   indistinguishable from a normal release to any consumer that doesn't
   independently verify the diff.
2. **A loose version constraint (`^1.2.0`, `>=1.0`) let the malicious
   version get pulled automatically** on the next `install`/CI run,
   without anyone reviewing it first, because the team optimized for
   "always get patches" over "review before adopting."
3. **CI/CD auto-merges dependency-bump PRs (Dependabot/Renovate) without
   a human or automated diff review gate**, so the compromised version
   reached production before anyone would have had a chance to notice
   anything odd even if they'd looked.
4. **No monitoring on the package's publish activity** -- most teams only
   watch for CVE disclosures, not for anomalous publish events (a new
   version published outside the maintainer's normal cadence, from a new
   or unverified npm/PyPI account tied to the package).

## Diagnose
- Compare the suspect version's published contents against the previous
  known-good version using the registry's own diff view or a local
  `diff -r` between two extracted tarballs -- focus on new files, newly
  added `postinstall`/build scripts, and any minified/obfuscated blocks in
  files that were previously plain source.
- Check the package's publish history and maintainer list on the registry
  for anything anomalous around the suspect version: a new maintainer
  added shortly before, publish from an unfamiliar IP-adjacent CI system
  (if the registry surfaces provenance), or a version bump that skips the
  project's normal changelog/release process (no matching GitHub release,
  no corresponding commit in the public repo).
- Check network egress logs from the build or runtime environment for
  connections to domains that have no legitimate relationship to the
  package's stated purpose, and check for outbound requests occurring at
  install time (during `postinstall`) rather than at declared runtime.
- Check whether the maintainer or project has posted an advisory --
  compromised-maintainer incidents are typically disclosed within days
  once discovered, on the project's GitHub, npm advisory database, or
  OSV.dev.

## Fix
Pin the affected dependency to the last known-good version immediately
(exact version, not a range) to stop further automatic pulls, and purge it
from any build caches or container image layers that might have baked in
the compromised version. Treat this as a security incident, not a routine
rollback: rotate any credentials or tokens that were present in
environments (CI runners, developer machines, production) where the
compromised version executed, since a malicious install script or runtime
code had access to that environment's secrets for the duration it ran.
Going forward, adopt exact version pinning (no `^`/`~`) for dependencies
combined with a deliberate, reviewed upgrade cadence (see this project's
`dependency-upgrade-strategy` pack) rather than always-latest, and require
that automated dependency-bump PRs pass through at least a diff-size/
script-change heuristic check before auto-merge is allowed.

## Pitfalls
- Assuming "it's a well-known, popular package, so this update is safe"
  -- popularity is exactly what makes a package's compromised maintainer
  account valuable to attack; trust in the package name does not transfer
  to trust in every future version.
- Rolling back the version without rotating credentials -- if the
  malicious code ran even once in an environment with secrets present,
  those secrets must be treated as exposed regardless of whether the
  rollback happened quickly.
- Re-enabling the loose version range immediately after pinning to the
  safe version "to not fall behind again" -- this recreates the exact
  condition that allowed automatic adoption of the malicious version in
  the first place; the fix is a reviewed upgrade process, not going back
  to auto-latest.

## Verify
Confirm the lockfile resolves to the exact known-good version across all
environments (local, CI, production images) by checking the resolved
version string, not just the declared range. Confirm no build artifact or
container image still contains the compromised version by grepping image
layers or build cache contents for the bad version string. Confirm
credential rotation completed by checking that any tokens active during
the exposure window have been revoked in the relevant provider's audit
log, not merely regenerated in a config file.
