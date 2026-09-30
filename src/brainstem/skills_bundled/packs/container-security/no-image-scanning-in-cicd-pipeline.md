---
name: no-image-scanning-in-cicd-pipeline
description: Vulnerable container images reach production unnoticed because the CI/CD pipeline builds and pushes images without any vulnerability scanning gate.
triggers: ["we have no image scanning step in our pipeline", "how do we add trivy to our github actions build", "vulnerable image deployed to prod with no scan catching it"]
permissions: ["READ"]
---

## Symptom
An incident review or routine audit reveals that a production image with multiple critical CVEs was deployed without ever having been scanned -- the CI/CD pipeline has stages for build, test, and push/deploy, but no stage inspects the resulting image for known vulnerabilities at any point before it reaches a running environment. This is different from "the scan ran but nobody acted on it" -- here, no scan runs at all, so there's no artifact, no report, and no historical record to even review after the fact.

## Likely causes
1. **Image scanning was never added to the pipeline template when it was first written**, and as more services were onboarded by copying that template, the gap propagated to every new service rather than being a one-off oversight.
2. **A scanning tool was evaluated once, produced a large number of findings that felt overwhelming to triage, and was quietly removed or left permanently in report-only/non-blocking mode** rather than tuned with a severity threshold, so it either doesn't run at all anymore or runs without consequence.
3. **Scanning exists for application dependency manifests (e.g. `npm audit`, Dependabot alerts) but not for the built container image itself**, missing OS-level package vulnerabilities in the base layer that dependency-file scanning can't see.
4. **The organization has multiple independent pipelines (per team, per repo) with no shared enforced template**, so scanning coverage is inconsistent -- some services have it, others were built by a team that never adopted it, and there's no central visibility into which is which.

## Diagnose
1. Pull the CI configuration for the affected service (GitHub Actions workflow, GitLab CI YAML, Jenkinsfile) and check for any invocation of an image scanner (`trivy image`, `grype`, `snyk container test`, `aqua`, ECR/GCR native scanning) between the build and push/deploy steps -- absence confirms the gap directly.
2. Check the container registry's own scan history/dashboard (ECR, GCR, Docker Hub, Harbor) for the image repository -- some registries scan on push independently of CI; if even that shows no scan results, there is truly zero coverage.
3. Audit across all service repositories, not just the one under review, for which pipelines include a scanning step versus which don't, to determine whether this is an isolated gap or systemic.
4. If a scanner was previously configured, check whether it's set to non-blocking (report-only, `exit-code 0` regardless of findings) -- this is a softer version of the same problem and should be checked for even when a scan step technically "exists."

## Fix
Add an image-scanning step to the pipeline immediately after the image build and before push/deploy, using a tool appropriate to the stack (Trivy and Grype are open-source and easy to drop into most CI systems; cloud-native registries also offer built-in scan-on-push). Configure it to fail the build on findings above an agreed severity threshold (commonly "fail on Critical/High with an available fix") rather than either blocking on everything (which becomes unmaintainable noise) or blocking on nothing (which is equivalent to not scanning). Roll this out via a shared, centrally-maintained pipeline template or reusable workflow so new services inherit scanning by default instead of depending on each team remembering to add it.

## Pitfalls
Setting the severity threshold to block on absolutely everything immediately after adding scanning is a common overcorrection that causes the whole team to lose trust in the gate within the first week, because it blocks releases on low-risk or no-fix-available findings -- start with a threshold that only blocks on high-confidence, fixable, high-severity issues, and tighten it over time as the backlog of pre-existing findings is worked down, rather than trying to reach zero-tolerance on day one.

## Verify
Confirm enforcement by deliberately introducing a base image with a known critical CVE in a test branch and confirming the pipeline fails the build at the scanning stage with a clear report of the finding. Then confirm a clean image passes through unimpeded, proving the gate discriminates correctly rather than blocking everything.
