---
name: unpinned-git-module-source-drift
description: A module sourced from a git tag or branch that got force-pushed or moved causes different team members and CI runs to apply different actual module code.
triggers: ["different terraform module code on different machines", "git tag moved terraform module", "terraform module source not reproducible", "force push broke terraform module", "terraform apply different results same commit"]
permissions: ["READ"]
---

## Symptom
Two team members (or a developer's laptop versus CI) run `terraform
plan`/`apply` against what appears to be the same configuration and the
same module source reference, but get different plans -- because the
actual module code each of them pulled down differs, even though the
`source` line in the `.tf` file hasn't changed and everyone believes
they're using "the same version."

## Likely causes
1. **The module source references a mutable git ref** -- a branch name
   (`?ref=main`) or a tag that isn't treated as immutable by convention
   (someone force-pushed a new commit onto an existing tag to "fix" it
   in place rather than cutting a new tag) -- so `terraform get`/`init`
   silently fetches whatever that ref currently points to, which can
   differ between two `init` runs done at different times.
2. **The module's git history was rewritten** (rebase, force-push to
   correct a mistake) after some consumers had already cached the old
   commit locally (`.terraform/modules`) while others fetch fresh and get
   the rewritten history, so the same tag name now resolves to two
   different commit SHAs depending on when/where `init` last ran.
3. **Local module caching masks the drift** -- once `terraform init` has
   populated `.terraform/modules` for a given ref, subsequent plans reuse
   the cached copy without re-fetching, so a developer who ran `init`
   before the force-push keeps using old code indefinitely while anyone
   who runs `init` fresh (a new CI runner, a clean checkout) gets the new
   code, and nothing prompts either side to notice the mismatch.
4. **No lockfile or checksum mechanism pins the module to a specific
   commit**, unlike provider version pinning via `.terraform.lock.hcl` --
   Terraform's module source mechanism for git/tag refs has no built-in
   equivalent guarantee of content-addressed immutability.

## Diagnose
- Compare the actual fetched module code across two environments showing
  different behavior: inspect `.terraform/modules/modules.json` for the
  resolved commit SHA each environment actually checked out for that
  module, rather than trusting the `ref=` string in the source line
  (which can be identical while the resolved SHA differs).
- Run `git ls-remote --tags <module-repo-url>` and compare the SHA the
  tag currently points to against the SHA recorded in each environment's
  `modules.json` -- a mismatch confirms the tag was moved after at least
  one environment had already resolved it.
- Check the module repository's reflog/tag history (if hosted with
  accessible history, e.g. GitHub's tag events or protected-tag audit
  log) for evidence of a force-push or tag re-creation around the time
  the discrepancy appeared.
- Ask affected team members when they last ran `terraform init` (versus
  reused an existing `.terraform` directory) -- the timing relative to
  when the tag moved determines which side has stale versus fresh code.

## Fix
Pin module sources to an immutable reference that can't be silently
moved: prefer a full commit SHA (`?ref=<full-sha>`) over a tag name where
the source repository's tagging discipline isn't fully trusted, or -- if
using tags -- enforce tag protection on the module repository itself
(branch/tag protection rules that block force-push and re-creation of
existing tags) so a tag, once cut, is truly immutable by policy, not just
by convention. Publish modules through a registry (a private Terraform
module registry, or the public registry for open-source modules) where
versions are content-addressed and immutable by the registry's own
guarantees, rather than relying on raw git ref semantics, whenever the
team's scale justifies the registry's operational overhead.

## Pitfalls
- Switching to full-SHA pinning without also documenting/automating the
  upgrade process makes module version bumps more tedious (copying a
  40-character SHA instead of a readable tag), which tempts teams to
  fall back to floating refs under time pressure -- pair SHA pinning with
  a simple bump workflow (a script or renovate/dependabot-style
  automation that opens a PR bumping the SHA) so the safety doesn't cost
  ongoing friction.
- Assuming `terraform init -upgrade` is required to pick up a moved tag's
  new content protects against drift -- it actually does the opposite for
  anyone who runs it after the force-push, since it explicitly re-fetches
  and will happily pull the moved tag's new (possibly unintended) content.

## Verify
After pinning to an immutable SHA (or enabling tag protection on the
module repo), have two different environments (a clean CI checkout and a
developer's fresh `.terraform` directory) both run `terraform init` and
compare the resolved module commit in each `modules.json` -- confirm both
resolve to the identical SHA, and confirm that attempting to force-push
over the pinned tag/SHA on the module repository is now rejected if tag
protection was the chosen fix.
