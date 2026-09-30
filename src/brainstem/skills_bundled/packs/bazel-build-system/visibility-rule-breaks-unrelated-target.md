---
name: visibility-rule-breaks-unrelated-target
description: Tightening a Bazel target's visibility to clean up dependency boundaries unexpectedly breaks a build for a seemingly unrelated target elsewhere in the repository.
triggers: ["bazel visibility broke unrelated build", "tightening visibility broke other target", "bazel dependency not visible error", "visibility change unexpected breakage"]
permissions: ["READ"]
---

## Symptom

A change intended to tighten a Bazel target's `visibility` attribute (to
enforce cleaner dependency boundaries between parts of a large
repository) causes a build failure in a target that seems completely
unrelated to the area being cleaned up, with an error about the target
not being visible to the dependent package.

## Likely causes

- **An unrelated-seeming target has a legitimate, working dependency on
  the target whose visibility was tightened**, discovered only because
  the visibility change surfaced it -- the "unrelated" target was never
  actually unrelated, just not obviously connected from the perspective
  of whoever made the visibility change.
- **A transitive dependency chain runs through the target being
  restricted** -- target A depends on B depends on C, and C's visibility
  was tightened without realizing A also needs to see C directly (not
  just through B) due to how Bazel's visibility model works with re-
  exports or a `alias` layer.
- **A test target, tooling target, or code-generation target depends on
  the internal target being restricted** for legitimate infrastructure
  reasons (a test harness reaching into implementation details, a
  codegen step) that wasn't accounted for when scoping the new, tighter
  visibility list.
- **The visibility change was made based on an incomplete dependency
  audit** -- checking obvious/direct callers but missing a reverse-
  dependency query that would have revealed every actual consumer before
  making the change.

## Diagnose

1. Read the exact error message for which target's visibility check
   failed and which consuming target triggered it.
2. Use `bazel query 'rdeps(//..., //path/to:target)'` (reverse
   dependency query) to get the complete, authoritative list of every
   target that actually depends on the target being restricted, before
   assuming a manually-compiled list was complete.
3. For the specific broken target, determine why it depends on the
   restricted target -- a legitimate architectural dependency, or itself
   evidence of an undesirable coupling worth addressing separately.
4. Check whether the dependency runs directly or transitively through
   another target, which affects what visibility change would actually
   be correct.

## Fix

Add the specific broken target (or its package) to the tightened
target's `visibility` list if the dependency is legitimate and
should be allowed to continue -- use the reverse-dependency query result
as the authoritative source for what needs to be included, not a
manually assembled guess. If the dependency reveals an undesirable
architectural coupling (the whole reason visibility tightening was being
done), address that coupling directly (refactor to remove the
dependency) rather than simply widening visibility back out to
accommodate it, which would defeat the purpose of the change.

## Pitfalls

Don't compile the new visibility list by manually reviewing code/
imports -- Bazel's own reverse-dependency query is the only reliable
source of truth for who actually depends on a target, since manual
review reliably misses non-obvious or transitive dependents, which is
exactly the failure mode this skill addresses. Also don't respond to one
broken build by reverting the visibility change entirely -- fix the
specific gap first, since the underlying goal (cleaner boundaries) is
usually still worth pursuing.

## Verify

Run a full reverse-dependency query against the tightened target again
after the fix and cross-reference it against the new visibility list to
confirm every actual consumer is accounted for. Run a full build (or at
least build every target the reverse-dependency query identified) to
confirm nothing else breaks.
