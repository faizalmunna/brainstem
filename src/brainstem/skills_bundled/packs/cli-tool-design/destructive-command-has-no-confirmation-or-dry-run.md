---
name: destructive-command-has-no-confirmation-or-dry-run
description: A CLI command that deletes data or makes an irreversible change executes immediately with no confirmation prompt or dry-run option, and a user accidentally runs it against the wrong target.
triggers: ["cli deleted wrong thing no confirmation", "destructive command no dry run", "accidental data loss cli tool", "no confirmation before irreversible action"]
permissions: ["READ"]
---

## Symptom

A user runs a command-line tool's delete, reset, or other irreversible
command against the wrong target (the wrong environment, the wrong
file, the wrong resource) because the command executed immediately with
no confirmation step and no way to preview what it would do beforehand
-- resulting in real, unrecoverable data loss or damage.

## Likely causes

- **The command was designed for speed/scriptability without a
  corresponding safeguard for interactive human use** -- a
  confirmation prompt would be inconvenient in automation, but no
  distinction was made between interactive and scripted invocation to
  apply the safeguard only where appropriate.
- **No dry-run mode exists** to preview exactly what a destructive
  command would do before actually doing it, so the only way to verify
  the target/scope is correct is to run it for real.
- **The command doesn't clearly display what it's about to affect**
  (which specific resources, how many records, which environment) before
  executing, so even a confirmation prompt (if one existed) wouldn't give
  the user enough information to catch a mistake.
- **A default target/scope is assumed** (the current directory, the
  currently-configured environment) that's easy to have set incorrectly
  without realizing it, especially if the user recently switched
  contexts and forgot.

## Diagnose

1. Identify the specific destructive commands in the tool (delete,
   reset, force-push equivalents, drop) and check whether each has any
   confirmation or preview mechanism.
2. Check whether the tool distinguishes interactive terminal use (where
   a confirmation prompt is appropriate) from scripted/automated use
   (where a prompt would break automation, and an explicit flag should
   bypass it instead).
3. For the specific incident, reconstruct what the user actually saw
   before running the command and what would have caught the mistake
   (a clearer target display, a confirmation, a dry-run preview).
4. Check whether a default target/scope was involved and whether it was
   clearly displayed or easy to overlook.

## Fix

Add a confirmation prompt for destructive commands run interactively
(detected via TTY check, consistent with this pack's terminal-detection
skill), clearly stating exactly what will be affected (specific
resource names/counts, the target environment) before proceeding, with
an explicit flag (like `--yes` or `--force`) to bypass the prompt for
scripted use. Add a dry-run mode (`--dry-run`) that shows exactly what
the command would do without actually doing it, available for any
destructive operation. Make the currently-active target/scope (an
environment, a configured context) clearly visible in the command's
output or a preceding status check, especially for tools that maintain
persistent context across invocations.

## Pitfalls

Don't make the confirmation prompt itself so routine/repetitive that
users develop a habit of blindly confirming without reading (confirmation
fatigue) -- make the prompt's content specific and meaningful each time
(showing the actual target) rather than a generic "are you sure? y/n"
that trains users to auto-confirm without looking.

## Verify

Attempt the destructive command interactively and confirm the
confirmation prompt displays accurate, specific information about what
will be affected. Confirm the `--yes`/`--force` bypass flag works
correctly for scripted use, and confirm the dry-run mode accurately
previews the operation's effect without actually performing it.
