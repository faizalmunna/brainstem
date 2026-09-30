---
name: no-sbom-generated-for-application
description: During an active supply-chain incident nobody can quickly answer whether the application actually uses the compromised library, because no software bill of materials exists.
triggers: ["are we affected by this vulnerable package", "need to know if we use this library anywhere", "no sbom for our application", "can't answer which apps use the compromised dependency during incident", "software bill of materials missing"]
permissions: ["READ"]
---

## Symptom
A supply-chain advisory breaks (a popular package is found compromised,
or a critical CVE is disclosed in a widely used library), and when
leadership or a security team asks "are we using this, and where," the
answer takes hours or days instead of minutes -- engineers have to
manually grep lockfiles across dozens of repositories, ask each team
individually, or discover mid-incident that some services' dependency
manifests aren't even checked into the repo they're deployed from. There
is no single, queryable inventory of what software (including transitive
dependencies and their versions) is actually running in production.

## Likely causes
1. **No SBOM generation step exists anywhere in the build/release
   pipeline** -- dependency information only ever existed as scattered
   lockfiles per-repository, never aggregated or exported in a
   standardized, machine-queryable format (CycloneDX, SPDX).
2. **SBOMs are generated but not kept current** -- a one-time SBOM was
   produced for an audit or compliance requirement and then never
   regenerated, so it reflects a dependency snapshot from months or years
   ago, which is worse than no SBOM if someone trusts it without checking
   its age.
3. **SBOMs exist per-repository but aren't aggregated across the
   organization** -- during an incident, someone still has to manually
   check every service's SBOM one at a time because there's no central
   index to query "which of our SBOMs contain package X," which doesn't
   scale past a handful of services.
4. **The SBOM only covers direct dependencies declared in the top-level
   manifest**, omitting transitive dependencies pulled in underneath --
   the compromised package in an actual incident is very often several
   levels deep in the tree, exactly where an incomplete SBOM won't show
   it.

## Diagnose
- Check whether any SBOM generation step exists in the CI/CD pipeline at
  all (search build configs for `cyclonedx`, `syft`, `spdx-sbom-generator`,
  or language-specific equivalents like `npm sbom`, `pip-audit --format
  cyclonedx`, `cargo cyclonedx`) -- absence confirms the gap directly.
- If SBOMs exist, check their generation timestamp against the most
  recent deployment/release -- an SBOM older than the last dependency
  change is stale and doesn't reflect what's actually running.
- Check whether the SBOM includes the full transitive dependency graph or
  only direct/top-level dependencies -- open a generated SBOM file and
  confirm it lists packages that aren't in the top-level manifest at all,
  which proves transitive resolution was captured.
- Simulate the actual incident-response question: pick a real, moderately
  deep transitive dependency and time how long it takes to determine,
  using only existing tooling, whether and where it's used across all of
  the organization's services -- if this takes longer than a few minutes,
  the current setup doesn't meet the bar this skill addresses.

## Fix
Add SBOM generation as a mandatory, automated step in the build pipeline
for every deployable artifact, using a standard format (CycloneDX or
SPDX) and a tool appropriate to the ecosystem, so it happens on every
build rather than as a manual, easily-forgotten one-off task. Generate it
from the fully resolved lockfile (post-resolution, not the hand-written
manifest) so transitive dependencies are captured completely, and attach
the SBOM as a build artifact alongside the deployable so each specific
deployed version has a corresponding, timestamped SBOM. For organizations
with many services, feed generated SBOMs into a central store or scanner
that supports querying across all of them at once ("which services
currently have package X at version Y") rather than leaving each SBOM as
an isolated file someone has to know to look for.

## Pitfalls
- Generating an SBOM once for compliance and treating the box as
  permanently checked -- an SBOM is only useful during an incident if
  it's current as of the version actually deployed; a stale SBOM can
  produce a false "we're not affected" answer that's worse than admitting
  the data doesn't exist.
- Producing SBOMs per-repository with no aggregation, which technically
  satisfies "we have SBOMs" but doesn't actually solve the underlying
  incident-response problem of answering "where" quickly across the whole
  organization.
- Treating SBOM generation as a security-team-only concern bolted on
  after the fact rather than a build-pipeline step -- if it's not wired
  into CI, it silently stops being generated the moment the person who
  set it up moves on or the process is forgotten.

## Verify
Confirm an SBOM file is produced and attached as a build artifact on a
fresh run of the pipeline for a real service, and open it to confirm it
lists transitive dependencies not present in the top-level manifest.
Confirm its timestamp/version metadata matches the exact commit or
release it was generated from. Then run the actual incident-response drill
again (pick a real transitive dependency, time how long it takes to
answer "are we using this and where") and confirm it now resolves in
minutes via a query rather than manual repo-by-repo inspection.
