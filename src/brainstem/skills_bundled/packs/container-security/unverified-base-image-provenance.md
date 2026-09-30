---
name: unverified-base-image-provenance
description: A widely used public base image or registry image could be silently swapped or compromised upstream and nothing in the pipeline would detect it before deployment.
triggers: ["how do we know this docker image wasn't tampered with", "should we verify image signatures before deploying", "supply chain attack on a public docker hub image"]
permissions: ["READ"]
---

## Symptom
The team pulls a public base image (from Docker Hub, a language ecosystem's official image, or a popular third-party image) by a floating or even pinned tag and deploys it with no step that verifies the image's signature, publisher identity, or build provenance. If that upstream image were ever compromised -- a maintainer account takeover, a malicious update to a popular image, a typosquatted name -- the pipeline would pull and deploy it exactly as it would any legitimate update, with no alert.

## Likely causes
1. **The pull step trusts tag/digest alone with no signature verification**, so `FROM library/node:18` or similar is accepted purely because the registry served something under that name -- registries authenticate *that a push happened*, not *who is trustworthy* or *that the content matches what was audited*.
2. **No admission-time enforcement in the cluster** (no Kyverno/Cosign policy, no `imagePolicyWebhook`) means even if some images are signed, nothing actually blocks an unsigned or invalidly-signed image from running.
3. **Base images are chosen for popularity/convenience rather than a vetted allowlist** -- a widely-used community image maintained by an individual has a very different compromise blast radius than an official, actively co-maintained one, but teams often don't distinguish between them when picking a `FROM` line.
4. **Internal images pushed by CI aren't signed either**, so even the organization's own supply chain (build server compromise, stolen registry credentials) has no cryptographic trail distinguishing a legitimate CI-built image from one pushed by an attacker with leaked credentials.

## Diagnose
1. Check whether the currently deployed images have any associated signature: `cosign verify <image>@<digest>` against expected public keys or a Sigstore/Fulcio identity -- if this fails or there's no policy calling it in the first place, verification is not happening today.
2. Review the CI/CD pipeline and admission controller config for any signature-verification step; grep for `cosign`, `notation`, `imagePolicyWebhook`, or Kyverno `verifyImages` policies -- absence confirms the gap.
3. Audit the actual `FROM` lines and registry pull sources across Dockerfiles for images pulled from unofficial/unverified namespaces (a personal Docker Hub account rather than an org-verified publisher) that could be swapped or abandoned-then-hijacked.
4. Check registry pull logs/audit trail for whether image digests referenced in deployments have changed unexpectedly for a tag that should be stable (a legitimate tag suddenly resolving to a wildly different digest with no corresponding release note is a red flag worth investigating retroactively).

## Fix
Adopt Sigstore/Cosign (or an equivalent like Notation/TUF-based tooling) to sign every image the organization builds in CI, and enforce verification at deploy time with an admission controller policy (Kyverno `verifyImages`, Connaisseur, or a cloud provider's native binary authorization) that rejects any image without a valid signature from a trusted identity. For third-party base images, prefer ones that publish provenance attestations (SLSA) or are Docker Official Images with an established maintenance record, and pin by digest rather than mutable tag so a later upstream compromise of that same tag name doesn't silently flow into your next build. Where the ecosystem supports it, verify upstream image signatures too, not just your own build outputs.

## Pitfalls
Treating "we pin by digest" as equivalent to "we verify provenance" is a common false sense of security -- pinning by digest only guarantees byte-for-byte immutability of *that specific pull*, it says nothing about whether the digest you pinned was ever legitimate in the first place if the initial pull happened during a compromised window. Provenance verification and digest pinning solve different problems and are both needed.

## Verify
Confirm enforcement is real, not advisory: attempt to deploy a deliberately unsigned test image against the cluster's admission policy and confirm it's rejected with a clear policy violation, not just logged as a warning. Then confirm a properly-signed image from the real CI pipeline deploys successfully, proving the policy discriminates correctly rather than blocking everything or nothing.
