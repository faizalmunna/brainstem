---
name: container-image-scan-blocks-on-unfixable-base-cve
description: A container image vulnerability scan blocks every deploy on a base-image CVE that has no available patch yet, freezing the release pipeline.
triggers: ["trivy blocking deploy on base image cve", "no fix available but scan still fails build", "container scan gate stuck on unpatched vulnerability", "cant deploy because of upstream base image cve", "image scanning gate frozen"]
permissions: ["READ"]
---

## Symptom
A container image scanner (Trivy, Grype, Clair, Snyk Container) is
wired into the deploy pipeline as a hard gate, and it starts failing
every build -- not because of anything the team changed, but because a
CVE was newly published against a package baked into the official base
image (e.g. a library in `python:3.12-slim` or `node:20-alpine`) with no
patched version available yet from the upstream image maintainer.
Because the gate has no way to distinguish "fixable now" from "not yet
fixable," every deploy is blocked indefinitely until upstream ships a
fix, even for application changes completely unrelated to the
vulnerable package.

## Likely causes
1. **The gate blocks on any finding above a severity threshold with no
   "fix available" condition**, so a CVE with `fix_status: not_fixed`
   is treated identically to one with a patched version sitting one
   `apt upgrade` away, even though only the latter is actionable right
   now.
2. **The base image is pinned to a tag that only updates on a slow
   cadence** (a specific minor version tag rather than tracking the
   maintainer's patched rebuilds), so even once upstream does patch it,
   the pipeline doesn't pick up the fix until the base image reference
   is manually bumped.
3. **No distinction is made between OS-package-level vulnerabilities in
   the base image and vulnerabilities in the application's own
   dependencies** -- the same gate and threshold applies to both, when
   the team's ability to act on each is very different (they can bump
   their own dependency immediately; they can't force an upstream base
   image fix).
4. **No time-boxed exception mechanism exists for "known, tracked,
   not yet fixable" findings**, so the only two options that feel
   available are "block everything" or "disable the gate," rather than
   a scoped, expiring allowance for the specific unfixable CVE.

## Diagnose
- Check the scanner's finding detail for a fix-availability field
  (Trivy reports `FixedVersion` as empty for unfixed CVEs, Grype
  similarly) to confirm whether this specific finding is genuinely
  unfixable right now versus fixable-but-unapplied.
- Check the base image's upstream repository/advisory tracker (e.g. the
  Alpine or Debian security tracker, the official image's GitHub repo)
  for the CVE's status -- confirm whether a fix is in progress upstream
  and get an approximate timeline if published.
- Check whether the pipeline gate configuration has any severity-only
  threshold with no fixability condition, versus a scanner flag like
  Trivy's `--ignore-unfixed` that's simply not being used.
- Check how the base image is referenced (exact digest pin vs. a
  floating tag) to determine whether picking up a future upstream fix
  will require a manual bump or happens automatically on next build.

## Fix
Configure the scanner/gate to separate "fixable now" from "not yet
fixable" findings rather than gating on severity alone -- most scanners
support an explicit flag for this (Trivy's `--ignore-unfixed`, Grype's
`only-fixed` config) so the blocking gate only fires on vulnerabilities
with an available remediation, while unfixed findings are still recorded
and tracked (a dashboard, a suppressed-with-expiry list) rather than
either silently dropped or block-everything. For the specific unfixed
CVE, add a time-boxed, ticket-linked exception (expiring in, say, 2-4
weeks or tied to the upstream advisory's expected fix date) so it
doesn't block unrelated deploys but also doesn't get forgotten once a
fix does ship -- pair this with a recurring check (or automated alert)
against the upstream tracker so the team notices when a fix becomes
available rather than relying on the next scan to surface it
incidentally.

## Pitfalls
- Blanket-enabling `--ignore-unfixed` (or equivalent) without a
  parallel tracking mechanism makes genuinely unfixed, exploitable
  vulnerabilities invisible indefinitely -- pair the gate change with
  continued visibility (dashboard/report), not just silence.
- Switching to a different, "cleaner" base image to dodge one CVE
  without evaluating its overall maintenance/patch cadence can trade one
  unfixable-CVE problem now for a worse one later if the new image is
  less actively maintained.
- Setting the exception's expiry far in the future "to be safe" defeats
  the purpose of time-boxing -- tie the expiry to a realistic re-check
  interval and actually revisit it, not a date chosen to avoid dealing
  with it again soon.

## Verify
After configuring fix-availability-aware gating, confirm a test build
with only the known-unfixed CVE present passes the gate (deploy is not
blocked) while the scan report still lists the CVE as tracked/pending,
and confirm a separately introduced *fixable* high-severity finding in
the same build still correctly fails the gate -- proving the gate now
discriminates on fixability rather than passing everything indiscriminately.
