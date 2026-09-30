---
name: stale-base-image-accumulating-known-cves
description: A container image built months ago from a base image now shows dozens of known CVEs in scans because nothing ever rebuilds it when the upstream base patches.
triggers: ["our image scanner flags 40 CVEs on a base image we haven't touched", "trivy shows critical vulns in a base image nobody updated", "why does this image have so many known vulnerabilities"]
permissions: ["READ"]
---

## Symptom
A vulnerability scanner (Trivy, Grype, Snyk, ECR scanning) reports a growing pile of known CVEs -- often dozens, many rated critical/high -- against an image that has otherwise been "working fine" in production for months. The application code hasn't changed; the CVEs are all in OS packages or the base image layer, and the count only ever goes up between scans.

## Likely causes
1. **The Dockerfile pins a base image tag that never changes** (e.g. `FROM node:18.4-slim` or a digest pin) and nothing bumps it, so the image is frozen at whatever patch level existed the day it was authored.
2. **CI only rebuilds on application code changes**, not on a schedule or in response to upstream base-image updates -- if `app/` hasn't changed, the pipeline has no trigger to rebuild even though the base image has shipped ten security patches since.
3. **The team conflates "using an official/verified image" with "safe forever"** -- official images (python, node, alpine, debian) get patched upstream constantly, but a pinned digest from six months ago carries none of those patches until something explicitly rebuilds against a newer one.
4. **No automated dependency/base-image update tooling** (Renovate, Dependabot, or a scheduled `docker build --pull`) is wired into the repo, so bumping the base tag is a manual, easily-forgotten chore.

## Diagnose
1. Run the scanner locally against the deployed image and inspect which layer each CVE traces to: `trivy image --format json myimage:prod | jq '.Results[] | select(.Class=="os-pkgs")'` -- if nearly all findings are OS packages rather than app dependencies, it's a base-image staleness problem, not an app problem.
2. Compare the base image's tag/digest in the Dockerfile against the current upstream digest: `docker buildx imagetools inspect node:18-slim` vs. what's actually pinned; a large digest/date gap confirms staleness.
3. Check CI history for the last time this image was actually rebuilt vs. the last time the Dockerfile changed -- if the last rebuild predates several upstream base-image releases, there's no rebuild trigger tied to base updates.
4. Look for the presence (or absence) of Renovate/Dependabot config (`renovate.json`, `.github/dependabot.yml`) covering Dockerfile `FROM` lines specifically -- many configs cover package.json/requirements.txt but forget Dockerfiles.

## Fix
Treat the base image as a dependency with its own update lifecycle, not a one-time choice. Add Renovate or Dependabot Docker-ecosystem support so `FROM` lines get automated PRs when the upstream tag moves, and pair it with a scheduled CI job (nightly or weekly) that rebuilds and rescans the image even when application source hasn't changed -- this catches the case where the base image gets patched but no one touches the app repo. Prefer floating minor tags with a scanning gate (`node:18-slim`, rebuilt regularly) over hard digest pins unless you have a deliberate, tracked promotion process for bumping the pin; a digest pin without an update process just moves the staleness problem to "someone has to remember."

## Pitfalls
Reacting to a stale-base-image finding by pinning the *exact current* digest "to stop the scanner from complaining" makes things worse -- it freezes the image at today's patch level with no mechanism to ever move forward, so the same CVEs return next month under a different CVE ID. Pin for reproducibility, but always pair the pin with an automated bump path, never a pin-and-forget.

## Verify
After wiring the automated rebuild/update path, confirm a test bump actually flows end-to-end: manually trigger the scheduled rebuild job, confirm it pulls a fresher base digest, and rerun the scanner to see the previously-flagged OS-package CVE count drop for that layer. Then confirm the Renovate/Dependabot PR for a `FROM` bump appears within one upstream release cycle without manual prompting.
