---
name: breaking-flag-rename-with-no-deprecation-warning
description: A CLI tool renames or removes a command-line flag in a new release with no deprecation warning in the prior version, silently breaking every script that used the old flag.
triggers: ["cli flag renamed broke scripts", "removed flag no warning", "cli breaking change no deprecation", "script broke after cli tool update"]
permissions: ["READ"]
---

## Symptom

After upgrading a command-line tool to a new version, scripts that
invoke it with a previously valid flag start failing with an "unknown
flag" error (or, worse, the flag is silently ignored rather than
erroring) -- the flag was renamed or removed in the new version, and the
previous version gave no warning that this was coming.

## Likely causes

- **The flag was renamed for clarity/consistency reasons without
  considering backward compatibility**, treating a CLI flag rename as
  equivalent to renaming an internal variable, when in practice it's a
  breaking change to every external script that uses it.
- **No deprecation period was used** -- the old flag was removed in the
  same release that introduced the new one, rather than supporting both
  (with a deprecation warning on the old one) for at least one release
  cycle before removal.
- **The tool has no formal versioning/compatibility policy** for its CLI
  interface, so flag changes are treated the same as any other code
  change rather than being recognized as a public contract with its own
  compatibility expectations.
- **The new flag's behavior isn't actually identical to the old one**
  (a subtle semantic difference alongside the rename), compounding a
  naming break with a behavioral one.

## Diagnose

1. Confirm the exact flag change (rename, removal, or semantic change)
   by diffing the tool's help output or changelog between the working
   and broken versions.
2. Check whether the tool's release notes/changelog documented this as a
   breaking change with a migration note, or whether it went
   unannounced.
3. Check whether the flag is silently ignored (accepted but has no
   effect) versus producing an explicit "unknown flag" error, since
   silent ignoring is the more dangerous failure mode (scripts appear to
   succeed while doing something different than intended).
4. Assess how many scripts/automation depend on the old flag to gauge
   the actual blast radius.

## Fix

Going forward, support both the old and new flag names for at least one
full deprecation cycle, with the old flag printing an explicit
deprecation warning (to stderr, not silently) pointing at the new flag
name, before actually removing the old one in a later release.
Explicitly document flag/interface changes in release notes with clear
migration guidance. For the current break, consider re-adding the old
flag name as a deprecated alias in a patch release to unblock affected
users while they migrate on their own schedule.

## Pitfalls

Don't silently accept an unknown/removed flag without at least a warning
-- silently ignoring an unrecognized flag (rather than either supporting
it or explicitly erroring) is worse than a hard error, since it lets a
script appear to succeed while actually running with different behavior
than the caller intended.

## Verify

Confirm the reintroduced deprecated flag (if added back) works
identically to before, with a visible deprecation warning printed.
Confirm the tool's release process now includes an explicit compatibility
check step for CLI interface changes before any future release.
