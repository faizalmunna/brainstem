---
name: abandoned-dependency-no-one-patching-new-vulnerabilities
description: A dependency the application relies on has had no maintainer activity in years, so newly discovered vulnerabilities in it will never be patched upstream.
triggers: ["is this package still maintained", "dependency hasn't been updated in years", "maintainer stopped responding to issues", "abandoned open source library still in use", "no fix coming for this vulnerability because project is dead"]
permissions: ["READ"]
---

## Symptom
A dependency-vulnerability scan or a routine dependency review turns up a
package the application has relied on for a long time, only to discover
its last release or commit was years ago, its issue tracker has dozens of
unanswered bug reports and security concerns, and there is no realistic
prospect of an upstream fix if a new vulnerability is found in it --
unlike the standard "known CVE with a fix available" case, this is about
discovering the *absence* of anyone able to respond at all, often only
noticed when a scan finds something and the team goes looking for a patch
that will never come.

## Likely causes
1. **The package was adopted years ago when it was actively maintained**,
   and nobody re-evaluates dependency health after initial adoption --
   maintenance status isn't a one-time check, it's a property that can
   decay silently over time with no notification mechanism.
2. **The dependency is a small, deep transitive dependency** that nobody
   directly chose or is even aware of using, making its abandonment
   invisible until a scan or incident specifically surfaces it -- unlike a
   direct dependency the team consciously picked and might track.
3. **A single-maintainer project lost its only maintainer** (they moved
   on, lost interest, or in rare cases died) with no succession plan, a
   common and well-documented failure mode for widely-used but
   under-resourced open-source infrastructure.
4. **The team conflates "no new CVEs reported" with "actively maintained
   and safe"** -- a project with no maintainer also generates no new CVE
   reports because no one is looking for or disclosing vulnerabilities in
   it responsibly, which can look identical to a genuinely secure,
   stable, feature-complete package on a vulnerability dashboard.

## Diagnose
- For each direct and significant transitive dependency, check the
  upstream repository's last commit date, last release date, and number
  of open issues/PRs with no maintainer response -- a repo with no commits
  in 2+ years and dozens of unaddressed issues is a strong abandonment
  signal regardless of how clean its vulnerability history looks.
  Automated tools exist for this at scale (e.g. checking `deps.dev` or
  similar dependency-health services that surface maintenance signals,
  not just vulnerability counts).
- Check whether the package has any listed alternative or is explicitly
  marked deprecated/archived by its own maintainers (a GitHub-archived
  repo, a README pointing to a successor project) -- this is the clearest
  possible signal and is often missed because nobody re-reads a
  dependency's README after initial adoption.
- Check how deeply the application actually depends on it -- is it a
  small utility easily replaced, or load-bearing with deep integration --
  since the remediation cost varies enormously and should be assessed
  before treating every abandoned dependency as equally urgent.
- Cross-reference the package against its ecosystem's own abandonment
  trackers where they exist (some registries or community projects
  maintain "unmaintained package" lists) to see whether the community has
  already identified and discussed this specific package's status.

## Fix
Establish a periodic (not one-time) dependency health review, separate
from vulnerability scanning, that checks maintenance signals (last
commit/release, issue responsiveness, archived status) across the
dependency tree, since this is a slowly-decaying property that a
point-in-time adoption decision can't catch later. For a confirmed-
abandoned dependency, prioritize replacement based on actual exposure --
network-facing or parsing untrusted input ranks higher than an internal
build-time-only utility -- and where full replacement isn't immediately
feasible, consider forking the specific dependency internally so the team
controls patching for any future vulnerability discovered in it, rather
than depending on an upstream that no longer exists in any practical
sense. Document the decision and monitoring plan for any abandoned
dependency that's knowingly kept, the same way this pack's other skills
recommend documenting a deliberately-deferred CVE fix, so it's a tracked
risk rather than a forgotten one.

## Pitfalls
- Treating "zero open CVEs" as equivalent to "safe to keep using
  indefinitely" -- an abandoned package's clean vulnerability history
  reflects lack of scrutiny, not lack of risk, and this is easy to
  conflate when reading a standard scanner dashboard.
- Forking an abandoned dependency and then never actually maintaining the
  fork either -- a fork only solves the problem if someone is genuinely
  committed to patching it going forward; an unmaintained fork of an
  unmaintained package is the same problem with extra steps.
- Waiting for a scanner alert to discover abandonment -- by definition, an
  abandoned package with no new disclosed CVEs will never trigger a
  scanner alert, so relying solely on scan results means this category of
  risk is systematically invisible until manually checked.

## Verify
For a dependency flagged as abandoned and slated for replacement or
forking, confirm the replacement is fully swapped in (no remaining
references to the old package in the resolved dependency tree, not just
the top-level manifest) and that the application's test suite passes
against the replacement. For a dependency kept and internally forked,
confirm the build actually resolves to the internal fork's package
source (check the lockfile's registry/source URL for that package) rather
than silently still pulling the original abandoned upstream package.
