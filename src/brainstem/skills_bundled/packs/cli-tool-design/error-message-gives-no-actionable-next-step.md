---
name: error-message-gives-no-actionable-next-step
description: A CLI tool's error message states that something failed but gives no indication of why or what the user should do to fix it, forcing a search through documentation or source code.
triggers: ["cli error message unhelpful", "generic error no fix suggestion", "cli tool error does not say what to do", "cryptic error message command line"]
permissions: ["READ"]
---

## Symptom

Running a command-line tool produces an error like "operation failed,"
"invalid input," or a raw stack trace/exception message, with no
indication of what specifically was wrong or what the user should do
differently -- forcing the user to search documentation, read source
code, or guess through trial and error to resolve something the tool
itself could have explained directly.

## Likely causes

- **Errors are propagated and printed at a generic top-level handler**
  (catching and printing an exception's default message) rather than
  being caught closer to the source with context-specific, actionable
  messaging added at each layer.
- **The specific validation or failure condition is known precisely in
  the code** (a missing required argument, an invalid file format, a
  network timeout) but the error message doesn't surface that specific
  detail to the user, using a generic message instead.
- **Error messages were written primarily for the tool's own developers
  during debugging** (an internal exception type name, a stack trace)
  rather than being rewritten for the actual end-user audience once the
  tool matured beyond early development.
- **No consideration was given to what the user should actually do
  next** -- the message states the failure but not the fix, even when the
  fix is straightforward and could be stated directly (e.g. "run `tool
  init` first").

## Diagnose

1. Collect a sample of the tool's actual error messages across different
   failure scenarios and assess each for whether it states what
   specifically went wrong and what the user should do about it.
2. For a specific unhelpful error, trace back to where it's actually
   generated/caught in the code and check what specific information was
   available at that point but not surfaced.
3. Check whether the tool has documentation that explains errors in more
   detail than the CLI output itself, which would confirm the underlying
   information exists but isn't being surfaced at the point of failure.
4. Survey actual user reports/support requests for confusion caused by
   specific error messages, to prioritize which ones matter most.

## Fix

Rewrite error messages to include both what specifically went wrong (the
actual invalid value, the specific missing file, the specific failed
precondition) and what the user should do about it (a suggested command,
a link to relevant documentation, a corrected example). Catch errors as
close to their source as possible, where the most specific context is
available, rather than letting a generic exception bubble up to a
top-level handler that's lost that context. Where a common error has a
clear, standard fix, state it directly in the error message rather than
just describing the problem.

## Pitfalls

Don't make error messages so verbose that the actual actionable
information gets buried in noise -- lead with the specific problem and
the specific fix, keeping any additional context (a stack trace, for
programmers using `--verbose`) available but not the default, primary
output.

## Verify

Trigger each previously-unhelpful error scenario again and confirm the
new message clearly states the specific problem and a concrete next
step, ideally verified by having someone unfamiliar with the tool's
internals successfully resolve the issue using only the error message.
