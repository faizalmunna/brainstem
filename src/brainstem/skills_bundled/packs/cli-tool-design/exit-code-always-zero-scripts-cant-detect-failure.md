---
name: exit-code-always-zero-scripts-cant-detect-failure
description: A command-line tool always returns exit code 0 regardless of whether the operation actually succeeded, making it impossible for scripts to detect failure programmatically.
triggers: ["cli always exits zero", "script cannot detect command failure", "exit code wrong on error", "cli tool not returning proper exit status"]
permissions: ["READ"]
---

## Symptom

A command-line tool prints an error message to the console when
something goes wrong, but its process exit code is still 0 (success),
so any script or CI pipeline invoking it (`if command; then ...`,
checking `$?`) can't actually detect that the operation failed --
only a human reading the console output would notice.

## Likely causes

- **The tool's error handling catches exceptions/errors and prints them,
  but the code path that would set a non-zero exit code was never
  implemented** -- the top-level entry point always returns/exits
  normally regardless of what happened inside.
- **A specific error condition is handled in a subcommand or nested
  function, but that failure status isn't propagated back up to the
  top-level process exit**, so an error three layers deep in the call
  stack never actually reaches the point where `process.exit(1)` (or
  the language equivalent) would be called.
- **The tool was built primarily for interactive human use**, where a
  printed error message was considered sufficient feedback, without
  considering that the same tool would later be used in
  non-interactive, scripted/automated contexts where exit codes are the
  only signal available.
- **A specific failure mode (a warning-level issue, a partial success)
  wasn't clearly categorized as success or failure**, so the
  implementation defaulted to treating it as success by omission rather
  than a deliberate choice.

## Diagnose

1. Reproduce a known failure condition and check the actual process exit
   code (`echo $?` on Unix-like shells, `$LASTEXITCODE` on PowerShell)
   immediately after running the command.
2. Trace the code path for that specific failure from where the error is
   detected/printed up to the top-level entry point, identifying exactly
   where the non-zero exit signal is lost or never set.
3. Check every distinct failure mode the tool has (not just one) for the
   same issue, since exit code handling bugs are often inconsistent
   across different error paths rather than uniformly broken.
4. Check any existing automated tests for whether they verify exit codes
   at all, or only check printed output, which would explain how this
   went unnoticed.

## Fix

Ensure every error/failure path in the tool ultimately results in a
non-zero exit code at the top-level process boundary, propagating
failure status explicitly through the call stack rather than assuming it
happens automatically. Use a consistent, documented exit code convention
(0 for success, specific non-zero codes for different failure
categories if the tool wants to support more granular scripting checks,
or simply 1 for any failure if that's sufficient) applied uniformly
across every command/subcommand. Add test coverage that explicitly
checks exit codes for both success and every known failure scenario, not
just printed output.

## Pitfalls

Don't make every warning or non-fatal issue also result in a non-zero
exit code as an overcorrection -- that breaks scripts that reasonably
expect a 0 exit code for a successful-but-imperfect operation; reserve
non-zero exit codes specifically for genuine failures the caller needs
to know about and react to.

## Verify

Re-run the tool against every known failure scenario and confirm each
now produces the correct non-zero exit code, verified via automated
tests that check exit codes specifically (not just console output).
Confirm a genuinely successful run still returns exit code 0.
