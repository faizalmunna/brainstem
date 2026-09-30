---
name: phantom-dependency-license-metadata-mismatch
description: A package's declared license, author, or repository metadata was silently changed in a later version, signaling a possible ownership or trust change worth investigating.
triggers: ["package license changed between versions unexpectedly", "repository link in package metadata points somewhere different now", "package metadata doesn't match what we remember", "author field changed on a dependency we didn't expect", "package.json repository url looks wrong"]
permissions: ["READ"]
---

## Symptom
While reviewing a dependency update, license-compliance scan, or an
unrelated audit, someone notices that a package's metadata -- its
declared license, listed author/maintainer, or linked source repository
URL -- differs from what it was in a previous version the team already
uses, even though the package's stated purpose and API surface look
unchanged. This is easy to dismiss as a clerical typo fixed upstream, but
it is also a documented pattern in real ownership-transfer and
account-takeover incidents: metadata changes are often the only visible
trace of a package changing hands before malicious code is introduced in
a subsequent release.

## Likely causes
1. **Legitimate ownership transfer** -- the original maintainer handed the
   package to a new maintainer or organization through a normal,
   announced transfer, and the metadata change is benign but was never
   communicated to downstream consumers who don't watch the project's
   announcements channel.
2. **A repository URL was changed to point to a fork or a completely
   unrelated repository** after an account or package-name takeover,
   while the package name and version-number sequence continue
   uninterrupted, making the change easy to miss since nothing about the
   install experience itself looks different.
3. **License field changes reflect a genuine relicensing decision** by the
   legitimate maintainers (which has real legal/compliance implications
   of its own) -- distinguishing this from a malicious takeover requires
   checking whether it was actually announced by the known-legitimate
   maintainers, not just assuming either way.
4. **Automated tooling or license scanners only check for license
   *type* compatibility (MIT vs. GPL) and never alert on the license or
   author field simply *changing* from a previous value**, so this signal
   is available in package metadata history but nothing in a standard
   pipeline surfaces it.

## Diagnose
- Compare the package's `package.json`/`setup.py`/equivalent metadata
  (author, license, repository URL, homepage) between the currently used
  version and the newest available version -- registries typically expose
  per-version metadata, or this can be done by diffing two downloaded
  tarballs directly.
- If the repository URL changed, visit both the old and new URLs and
  check whether the new one is a genuine continuation (same commit
  history, same contributor list, explicit transfer announcement in
  README or a pinned issue) or an unrelated/near-empty repository that
  doesn't match the package's actual history.
- Check the package's registry page for an explicit ownership-transfer
  announcement or new-maintainer-added event around the same version
  where the metadata changed -- legitimate transfers are usually
  announced; silent metadata changes with no corresponding communication
  are the more suspicious pattern.
- Check whether the change coincides with any other anomaly already
  covered elsewhere in this pack -- a new, unfamiliar transitive
  sub-dependency introduced in the same version, obfuscated code, or new
  install scripts -- since a metadata change alone is a signal to look
  harder, not proof of compromise by itself.

## Fix
Treat an unexplained metadata change (author, license, or repository URL)
as a trigger for the same scrutiny this pack applies to a suspicious new
transitive dependency or a suspect release from a trusted package: diff
the actual code contents against the previous version, check for new
install-time scripts, and confirm the change against an independent
source (the project's own announcement channel, not just the registry
listing, since the registry listing is exactly what would be controlled
by an attacker who took over the package). If the change can't be
confirmed as a legitimate, announced transfer, pin to the last version
before the metadata change and treat upgrading past it as blocked pending
investigation, the same way an unresolved security concern would block an
upgrade. Where the ecosystem's tooling supports it, add metadata-change
detection (author/license/repository field diffs across versions) as a
dependency-update review step, not just a version-number and changelog
review.

## Pitfalls
- Dismissing a metadata change as "probably just a typo fix" without
  checking the repository link itself -- the whole value of this signal
  is that it's often the only visible trace before a more damaging
  change appears in a later version, so treating it as cosmetic defeats
  the purpose of noticing it at all.
- Only reviewing metadata changes for the *license* field because that's
  what a compliance tool already surfaces, while ignoring author and
  repository URL changes that the same tooling typically doesn't track at
  all.
- Blocking every metadata change indefinitely without ever investigating
  and resolving it -- as with other deliberately-deferred decisions in
  this pack, an unresolved block should be a tracked, time-bound
  investigation, not a permanent freeze that quietly accumulates version
  debt.

## Verify
After investigating a flagged metadata change, document the conclusion
(confirmed legitimate transfer with a link to the announcement, or
confirmed malicious and remediated) alongside the specific version where
it occurred, so a future reviewer doesn't have to redo the same
investigation. If proceeding with the upgrade, confirm the new
repository/author is verifiably linked to the previously legitimate
maintainer (a cross-link from the old account, a signed announcement, or
continuity in commit history/contributors) rather than accepting the new
metadata at face value from the registry listing alone.
