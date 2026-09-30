---
name: stale-scanner-misses-known-cves
description: An outdated SAST or DAST tool version silently misses vulnerability classes and CVEs that a current version would catch.
triggers: ["scanner didnt catch a known vulnerability", "our sast tool is out of date", "why didnt zap find this cve", "vulnerability database looks stale", "scanner version is a year old"]
permissions: ["READ"]
---

## Symptom
A SAST or DAST tool has been running in CI for a long time without
anyone updating its binary/engine version or its rule/signature
database, and a vulnerability that should be well within its detection
capability -- a known CVE in a bundled component, a common injection
pattern the tool's vendor added coverage for two versions ago -- passes
through undetected, only surfacing later via a manual pentest, an
external report, or an actual incident, at which point it becomes clear
the tool version in use predates the detection logic entirely.

## Likely causes
1. **The tool's engine/binary is pinned to an old version with no update
   process**, common when a SAST/DAST tool was set up once in CI via a
   pinned Docker image tag or downloaded binary and never revisited,
   so it keeps running with whatever rule/query logic existed at setup
   time indefinitely.
2. **The vulnerability signature/rule database is separate from the
   engine version and updates on a different cadence** (e.g. a DAST
   tool's plugin/scan-policy definitions, a SAST tool's community rule
   pack) -- updating the engine binary doesn't automatically pull the
   latest signatures, and teams often update one without realizing the
   other is also stale.
3. **Air-gapped or offline scanning environments can't reach the
   vendor's update servers**, so the tool silently continues operating
   on whatever database was bundled at last manual import, with no
   automatic alert that it's aging.
4. **Version pinning was done deliberately for CI stability/reproducibility
   reasons** (avoiding a scanner update introducing new noise
   mid-sprint) and the pin was never revisited on any schedule, turning
   a reasonable short-term stability choice into permanent staleness.

## Diagnose
- Check the exact pinned version of the scanner in CI config (Docker
  image tag, package version, binary download URL) and compare against
  the vendor's current release and changelog to see how many versions/
  months behind it is and what detection capability was added since.
- Check the separate rule/signature database version/timestamp if the
  tool distinguishes engine from database (many do) -- an up-to-date
  engine with a stale database is a distinct and common variant of this
  problem from an entirely stale install.
- Look up whether the specific CVE or vulnerability class that was
  missed has a corresponding rule/check in the vendor's changelog or
  release notes, and note which version introduced it -- this confirms
  whether it's a coverage gap due to staleness (fixable by updating) or
  a genuine detection limitation of the tool (not fixable by updating
  alone).
- Check whether there's any automated process (Dependabot-style version
  bump, a scheduled CI job) keeping the scanner itself updated, versus
  it having been manually set up once with no ongoing maintenance
  owner.

## Fix
Treat the scanning tool itself as a dependency that needs an update
cadence, not a one-time setup: pin to a specific version for
reproducibility but establish a scheduled review (monthly or aligned
with the vendor's release cadence) to bump both the engine and the
signature/rule database, testing the update in report-only mode first
to catch any new-noise regression before promoting it to the blocking
CI gate (same pattern as adopting a new rule pack). For tools with
separately-versioned rule databases, ensure the update process refreshes
both, not just the binary. For air-gapped environments, establish a
periodic manual database import process with an explicit
staleness-check alert (e.g. fail loudly if the local database is older
than N days) rather than silent indefinite staleness.

## Pitfalls
- Auto-updating the scanner to "latest" on every CI run without pinning
  trades staleness for unpredictability -- an unreviewed scanner update
  can introduce new rules that suddenly fail builds with no warning,
  which is its own version of the "new rule set floods legacy code"
  problem; pin-and-scheduled-review beats always-latest for CI stability.
- Updating only the engine binary and assuming the rule/signature
  database came along with it (or vice versa) leaves partial staleness
  that's easy to miss since the tool still runs and reports findings
  normally, just without the newest coverage.
- Treating a scanner update as purely a maintenance/ops task with no
  security review of what new coverage it adds skips the chance to
  proactively check whether newly-added rules reveal anything in the
  existing codebase.

## Verify
After updating, check the tool's reported engine and database version
strings match the intended target versions, and re-scan a known test
case (a deliberately vulnerable sample app or a documented CVE
reproduction) that corresponds to a check added after the old version's
release date, confirming the updated tool now flags it where the old
version did not.
