---
name: direct-bump-pulled-transitive-with-silent-behavior-change
description: Upgrading a direct dependency also pulled in a new transitive dependency version, and the application silently relied on the old transitive's behavior, which changed without any intentional change to the direct dependency's own API.
triggers: ["upgraded one package and something else changed behavior", "a library I never touched started behaving differently", "transitive dependency changed with my direct upgrade", "behavior changed in a package I don't even directly depend on"]
permissions: ["READ"]
---

## Symptom

A direct dependency is upgraded for unrelated reasons -- a feature, a
security fix. Nothing in the direct dependency's own public API changed in
the diff, yet some application behavior changes anyway: a format, a sort
order, a default timeout, a serialization detail, a validation rule. The
change traces to a *transitive* dependency: the direct bump's new manifest
pulled in a newer version of a package the app never imports directly but
depends on indirectly, and the app was silently relying on the old
transitive's behavior through an intermediate layer.

## Likely causes

- **The direct bump's new version raised a constraint on a shared
  transitive**, so the resolved transitive jumped further than the direct
  dependency did -- often several major versions in a single upgrade.
- **The app's behavior depended on the transitive's implementation detail**
  (a default, a format, a sort order, error semantics) without ever
  declaring that dependency -- it was "felt" rather than "used," so nothing
  pinned it and no test asserted the behavior.
- **The change arrived solely through the lockfile refresh**, so the commit
  diff shows no code change, making the behavior change look unreproducible
  or unrelated to the upgrade.
- **The direct dependency's own tests pin only its direct dependencies**,
  so the specific version combination the app shipped was never exercised
  anywhere before it reached production.

## Diagnose

1. Diff the lockfile across the upgrade and list every *indirect/transitive*
   version that changed, even ones nobody intended to touch.
2. For each changed transitive, read its changelog for behavior-level notes
   (defaults, formats, semantics) and grep the app's dependency tree for
   re-exports -- a framework or intermediary that re-exports the transitive
   makes it reachable without a direct declaration in your own code.
3. Reproduce by reverting *only the transitive* in the lockfile: pin the
   old transitive while keeping the direct bump, and check whether the
   behavior change disappears.
4. Identify which layer of the app actually consumes the behavior -- that
   layer is where a characterization test belongs.

## Fix

Treat the lockfile diff as part of the upgrade's review surface: a direct
bump PR should call out transitive version jumps and their changelogs, not
just the direct dependency's, since those are where silent behavior changes
live. For any transitive the app demonstrably relies on (proven by "pin it
back and the behavior returns"), promote it to an explicit, directly
declared dependency with a version range you control, and pin the relied-upon
behavior in a characterization test so a future indirect swing fails CI
instead of shipping silently. Where the direct dependency's loose constraint
range is what permits the large transitive jump, prefer allowing a specific
range over an open-ended "latest."

## Pitfalls

Don't respond to a transitive behavior change by adjusting the app's code
to match the new behavior without first establishing which transitive
changed and whether its new version is the intended end state -- you may be
codifying a behavior that changes again at the next indirect bump, when the
durable fix is declaring and pinning the transitive you actually rely on.
Fixing symptom-side code treats the aftermath as a feature.

## Verify

Confirm attribution: pin the involved transitive to its pre-bump version
with the new direct dependency present and check that the original behavior
returns. Then, after promoting the transitive to an explicitly declared and
pinned dependency at its intended version, confirm that the characterization
test for the relied-upon behavior now exists and would fail if the
transitive were reverted to the old (or any other) version.