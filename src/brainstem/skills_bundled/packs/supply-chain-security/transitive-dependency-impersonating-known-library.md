---
name: transitive-dependency-impersonating-known-library
description: A malicious package with a name nearly identical to a trusted, well-known library sits undetected deep in the transitive dependency tree for months.
triggers: ["suspicious package in lockfile I don't recognize", "transitive dependency looks like it's impersonating a popular library", "malicious package hiding in node_modules", "audit found a package pretending to be eslint plugin", "unfamiliar dependency nobody remembers adding"]
permissions: ["READ"]
---

## Symptom
While reviewing a lockfile, bundle analyzer output, or a `node_modules`/
`site-packages` listing for an unrelated reason, someone notices a package
name that looks almost right but isn't -- e.g. an ESLint-plugin-sounding
package, or a scoped package under a name close to a well-known
maintainer/org, that nobody on the team can explain adding directly. It has
been resolving into builds for a long time because it's several levels deep
in the transitive tree and vulnerability scanners never flagged it (it has
no known CVE -- it was never a legitimate package with a disclosed flaw, it
was malicious from day one).

## Likely causes
1. **Nobody audits transitive dependencies for identity, only for known
   CVEs.** Standard scanners (`npm audit`, `pip-audit`, Dependabot) match
   package names/versions against vulnerability databases; a package that
   has never been reported as vulnerable -- because it was malicious from
   publication, not later compromised -- produces zero alerts no matter how
   long it sits in the tree.
2. **A direct dependency's own dependency list was quietly changed** (the
   direct dependency's maintainer added it, possibly also compromised, or
   a lockfile resolution picked a version range that happened to include
   it) and nobody re-reviews a direct dependency's transitive footprint
   after the initial adoption decision.
3. **The package name is a deliberate near-miss of a trusted name** (extra
   hyphen, transposed letters, a plausible scope prefix) designed to pass a
   glance during code review or a quick lockfile diff -- human pattern
   matching on package names is unreliable at scale.
4. **CI/build systems don't fail or alert on new, low-reputation packages
   entering the lockfile** -- there's no policy gate on package age,
   download count, or maintainer history, so anything that resolves
   installs silently.

## Diagnose
- Generate a full flattened dependency list (`npm ls --all`, `pip list`,
  or an SBOM per `no-sbom-generated-for-application` in this pack) and
  diff package *names* (not just versions) against the previous known-good
  baseline to surface anything new.
- For any unfamiliar package, check its registry page: publish date,
  number of versions, download counts relative to its apparent purpose,
  and whether the listed maintainer/repo link actually resolves to a real,
  active GitHub org -- a package claiming to be an ESLint plugin with near
  zero GitHub stars and a first-ever version published recently is a red
  flag.
- Check what pulled it in: `npm ls <package>` or `pip show` reverse
  dependency tracing shows the parent package(s) responsible; investigate
  whether that parent's own registry history looks normal at the time the
  dependency was added.
- Search the package's source (not just its `package.json`/`setup.py`
  metadata) for install-time scripts (`postinstall`, `preinstall`) that
  make network calls, read environment variables, or access credential
  files -- this is the most common payload delivery mechanism for this
  attack pattern.

## Fix
Treat transitive dependency identity as a distinct audit surface from
vulnerability scanning: periodically (not just at install time) generate
a flattened list of every package name actually resolving into the build
and spot-check unfamiliar entries against registry metadata, independent
of whether any scanner has flagged them. Where the ecosystem supports it,
enable lockfile-level pinning combined with a package-manager setting that
blocks install scripts by default (`npm config set ignore-scripts true`,
or per-package script allowlisting) so a newly introduced malicious
package can't execute arbitrary code just by being installed, even before
anyone reviews it. Once identified, remove the specific compromised
package via a lockfile override forcing the offending sub-dependency to a
known-safe alternative or version, verify it disappears from the flattened
tree, and rotate any credentials that were present in the build/CI
environment while the package was capable of running install scripts.

## Pitfalls
- Assuming a clean `npm audit`/Dependabot report means the dependency tree
  is safe -- these tools only match against disclosed-vulnerability
  databases and are structurally blind to packages that are malicious by
  design and have never been "disclosed" as anything.
- Removing the malicious package from the lockfile without checking
  whether its install scripts already ran in a prior CI build or ran
  during local development -- the exposure window may predate the
  discovery, so credential rotation is still needed even after removal.
- Relying on visual package-name review alone during PR review -- typo-
  adjacent names are specifically designed to defeat this, and it doesn't
  scale past a handful of direct dependencies anyway.

## Verify
Re-run the flattened dependency listing after remediation and confirm the
specific package name no longer appears anywhere in the tree (not just
that the direct dependency that pulled it in was updated -- confirm the
transitive resolution actually changed). Separately confirm `ignore-scripts`
or the equivalent install-script gate is active by attempting to install a
throwaway package with a known `postinstall` script and confirming it does
not execute.
