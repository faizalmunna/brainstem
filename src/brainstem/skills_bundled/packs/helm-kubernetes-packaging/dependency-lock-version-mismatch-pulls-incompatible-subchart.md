---
name: dependency-lock-version-mismatch-pulls-incompatible-subchart
description: A chart dependency's loose version constraint in Chart.yaml lets helm dependency update pull an unexpectedly incompatible subchart release.
triggers: ["helm dependency update pulled breaking version", "chart.lock out of date", "subchart version mismatch breaking chart", "helm dependency build wrong version pulled", "chart.yaml version range too loose"]
permissions: ["READ"]
---

## Symptom
A chart that has worked fine for months suddenly fails to render, fails
to install, or installs but the subchart's resources behave completely
differently, right after someone ran `helm dependency update` (often as
a routine "refresh deps" step, sometimes as an unnoticed side effect of
CI regenerating `Chart.lock`). Diffing the subchart's actual pulled
version shows a jump the team didn't intend, tracing back to a version
range in `Chart.yaml` that was looser than assumed.

## Likely causes
1. **A caret/tilde-style range in `Chart.yaml`'s `dependencies[].version`
   that's wider than intended** -- e.g. `version: "^11.0.0"` was written
   expecting only patch/minor bumps within a stable line, but the
   subchart's maintainers ship a major-version-equivalent breaking change
   under a minor version bump (common with community charts that don't
   follow strict semver on values-schema changes even if the app version
   itself does), and the range doesn't protect against that.
2. **`Chart.lock` was deleted or not committed to version control**,
   so every fresh `helm dependency build` (which is supposed to use the
   lock file for reproducibility) instead falls through to `helm
   dependency update` behavior against the live repository index,
   re-resolving the version range against whatever is currently latest
   rather than what was actually tested.
3. **CI pipeline runs `helm dependency update` instead of `helm
   dependency build`** -- `update` always re-resolves ranges against the
   remote repo index and rewrites the lock file, while `build` installs
   exactly what's pinned in the existing `Chart.lock`; a pipeline using
   `update` on every run defeats the purpose of committing a lock file at
   all and silently drifts forward over time.
4. **The subchart's own transitive dependencies changed** even though the
   subchart's own version constraint in the parent looks unchanged --
   the subchart itself has a dependency range on something else
   (a common base chart, an image tag default) that moved, and the parent
   chart has no visibility into or pinning of that second-level
   dependency at all.

## Diagnose
- Run `git diff` on `Chart.lock` (if committed) to see exactly which
  dependency versions changed and when, correlated against `git blame`
  on `Chart.yaml`'s version constraints to see if the constraint itself
  or just the resolved lock changed.
- Run `helm dependency list <chart>` and compare the "version" (the
  constraint) against the "resolved" column (the actual version present
  in `charts/`) -- a wide gap between what the constraint technically
  allows and what's now resolved indicates the range is looser than the
  team's mental model of it.
- Check the subchart's own changelog/release notes between the old
  pinned version and the new resolved version for explicitly called-out
  breaking changes to values schema, template output, or default
  resource behavior.
- Confirm which command the CI pipeline actually runs -- `grep -r "helm
  dependency" .ci/ .github/ Makefile` (or equivalent) -- `update` vs.
  `build` is the single most common root cause of "it worked yesterday
  and not today with no chart code changes."

## Fix
- Pin dependency versions to an exact version or a narrow patch-only
  range in `Chart.yaml` for anything where an unreviewed breaking change
  would be costly: `version: "11.4.2"` or `version: "~11.4.0"` rather
  than `^11.0.0`, treating any intentional upgrade as a deliberate,
  reviewed PR that bumps the constraint explicitly.
- Commit `Chart.lock` to version control, and change CI to run `helm
  dependency build` (which respects the committed lock file) rather than
  `helm dependency update` for normal installs/deploys -- reserve `helm
  dependency update` for an explicit, human-initiated "I want to bump
  dependencies now" action that also regenerates and commits the new
  lock file as part of that same change.
- When intentionally bumping a subchart version, do it as its own PR:
  update the constraint, run `helm dependency update` locally, review
  the subchart's changelog and the resulting `helm template` diff, and
  commit the updated `Chart.lock` alongside the constraint change so
  reviewers see both together.
- For transitive dependencies the team can't directly pin, vendor the
  subchart (commit the fetched `.tgz` under `charts/` directly instead of
  relying on live repository resolution) if reproducibility matters more
  than convenience for that particular dependency.

## Pitfalls
- Pinning every dependency to an exact version and never revisiting it
  accumulates security and bugfix debt silently -- exact pinning solves
  the surprise-breakage problem but needs a periodic, deliberate review
  cadence (e.g. a scheduled dependency-bump PR) or it just trades one
  risk for another.
- Regenerating `Chart.lock` locally on a machine with a different, stale
  local repository cache than CI can produce a lock file that resolves
  differently once pushed -- always run `helm repo update` immediately
  before `helm dependency update` when intentionally bumping, so the
  local resolution matches what CI would see.

## Verify
Run `helm dependency build` (not `update`) in a clean checkout and
confirm the resolved versions in `charts/` exactly match what
`Chart.lock` specifies with no network-driven re-resolution occurring;
then run `helm template .` before and after any intentional dependency
bump and review the full diff of rendered output, not just the version
number change, before merging.
