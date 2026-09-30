---
name: compromised-cicd-plugin-affects-every-subsequent-build
description: Every build run after a certain date is potentially compromised because a CI/CD platform plugin or extension itself was hijacked, not the application's own dependencies.
triggers: ["ci plugin might be compromised", "build tooling itself hacked not our dependencies", "jenkins plugin marketplace suspicious update", "github action pulled a malicious update", "every build since a certain date is suspect"]
permissions: ["READ"]
---

## Symptom
A security advisory or internal investigation reveals that a plugin,
extension, or reusable action used by the CI/CD platform itself (a Jenkins
plugin, a GitHub Action referenced by tag, a GitLab CI component, a build
tool's own plugin ecosystem) was compromised for some period of time --
meaning the compromise potentially affected every single build that ran
during that window, regardless of what the application's own
`package.json`/`requirements.txt` declared, because the malicious code ran
as part of the pipeline's own execution, with access to secrets, artifacts,
and deployment credentials for every job it touched.

## Likely causes
1. **A third-party GitHub Action or CI plugin is referenced by a mutable
   tag or branch name** (e.g. `uses: some-org/action@v1` or `@main`
   instead of a pinned commit SHA), so the action's maintainer -- or
   anyone who compromises that maintainer's account -- can silently change
   what code executes in every pipeline referencing it, with no new commit
   or PR on the consuming side to review.
2. **CI plugin marketplaces (Jenkins Plugin Manager, VS Code/IDE
   extension stores used in dev-container builds, etc.) have the same
   compromised-maintainer risk as package registries**, but teams often
   don't apply the same scrutiny to build tooling that they apply to
   application dependencies, treating "infrastructure" as inherently more
   trustworthy.
3. **The pipeline grants broad secret/credential access to every step by
   default**, including third-party actions/plugins, rather than scoping
   secrets narrowly to the specific steps that need them -- so a
   compromised plugin has a much larger blast radius than it would with
   least-privilege secret scoping.
4. **No integrity verification exists for build tooling itself** -- unlike
   application dependencies which may have lockfile hashes, ad-hoc CI
   plugin/action references are frequently unpinned and unverified,
   because they're perceived as "config" rather than "code that runs with
   privileged access."

## Diagnose
- Audit every third-party action/plugin reference in CI configs for
  whether it's pinned to an immutable commit SHA versus a mutable tag or
  branch -- grep `.github/workflows/*.yml` for `uses:` lines without a
  40-character SHA, or equivalent for the platform in use (Jenkinsfile
  plugin declarations, GitLab CI `include:` refs).
  Command example: search workflow files for `uses:\s*[^@]+@(?!.*[0-9a-f]{40})`
  style patterns to find tag/branch-pinned actions.
- For any plugin/action flagged by an advisory, check its publish/release
  history for the specific window of compromise, and cross-reference
  against CI run history to determine exactly which builds executed
  during that window -- every artifact and deployment produced by those
  runs is now suspect, not just the plugin itself.
- Check what secrets/credentials were accessible to the pipeline steps
  that used the compromised plugin -- review the job's secret scoping
  configuration, not just assume "it only had access to what it needed."
- Check build/deploy logs from the suspect window for anomalous outbound
  network activity or unexpected artifact modifications originating from
  the plugin's execution step specifically, distinguishing it from the
  application's own build steps.

## Fix
Pin every third-party CI action/plugin reference to an immutable commit
SHA (not a tag, not a branch), treating build tooling with the same
integrity bar as application dependencies -- this makes any future
update to the action an explicit, reviewable change in the consuming
repo's own CI config, rather than a silent swap outside anyone's review.
Scope secrets narrowly per job/step rather than granting broad credential
access pipeline-wide, so a compromised plugin's blast radius is limited
to what that specific step actually needed. When a compromise is
confirmed, treat every build and deployment that ran during the affected
window as potentially compromised: rotate every credential those builds
had access to, and re-verify (not just re-deploy) artifacts produced
during that window rather than assuming only the plugin's own output was
affected.

## Pitfalls
- Pinning application dependencies carefully while leaving CI
  actions/plugins on mutable references -- this is the same underlying
  mistake as unpinned Docker tags, applied to a part of the system teams
  often don't think to audit at all because it "isn't a dependency."
  See `unpinned-mutable-dependency-source-non-reproducible-build` in this
  pack for the parallel application-dependency case.
- Rotating only the credentials directly used by the deployment step and
  missing secrets that were merely *accessible* to the compromised
  plugin's execution context (environment-wide secrets, cloud provider
  credentials mounted for unrelated later steps in the same job).
- Assuming a compromise is contained once the plugin/action is unpinned
  or removed -- artifacts and deployments already produced during the
  compromise window remain suspect until independently re-verified, not
  merely because the pipeline is now fixed going forward.

## Verify
Grep the full CI configuration again after remediation and confirm zero
third-party action/plugin references remain pinned to a mutable tag or
branch -- every one resolves to a fixed commit SHA. Confirm credential
rotation by checking the provider's audit log for revocation of every
token/secret that was accessible during the compromise window, not just
regeneration in a config file. Confirm re-verification of affected build
artifacts by comparing their contents/hashes against a rebuild from the
same source using confirmed-clean tooling.
