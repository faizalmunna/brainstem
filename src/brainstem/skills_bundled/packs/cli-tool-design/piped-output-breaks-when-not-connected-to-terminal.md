---
name: piped-output-breaks-when-not-connected-to-terminal
description: A command-line tool's output includes color codes, progress bars, or interactive prompts that corrupt output or hang the process when run in a script or piped to another command.
triggers: ["cli output corrupted when piped", "ansi codes in piped output", "cli hangs in script not interactive", "tool breaks when redirected to file"]
permissions: ["READ"]
---

## Symptom

A command-line tool works fine when run interactively in a terminal, but
when its output is piped to another command, redirected to a file, or
run inside a script/CI pipeline (a non-interactive, non-TTY context),
the output is corrupted with visible escape codes, a progress bar
renders garbage, or the process hangs waiting for interactive input that
will never come.

## Likely causes

- **The tool unconditionally emits ANSI color/formatting escape codes**
  without checking whether the output stream is actually connected to a
  terminal that can interpret them, so a file or pipe destination
  receives the raw, uninterpreted escape sequences as literal garbage
  text.
- **A progress bar or spinner writes carriage-return-based updates**
  (overwriting the same line) that only makes sense on an interactive
  terminal, producing a flood of separate lines or garbled output when
  captured to a file or pipe.
- **The tool prompts for interactive confirmation** (a yes/no question,
  a password entry) without checking whether standard input is
  actually connected to an interactive terminal, causing it to hang
  indefinitely waiting for input in a non-interactive context like a CI
  pipeline.
- **The tool assumes a specific terminal width for formatting output**
  (wrapping text, aligning columns) which is meaningless or produces
  odd results when output isn't going to an actual terminal.

## Diagnose

1. Reproduce the issue explicitly by piping the tool's output to a file
   or another command (`tool | cat`, `tool > output.txt`) and inspect the
   actual raw output for escape codes or corruption.
2. Check the tool's implementation for whether it checks TTY status
   (`isatty()` or the language equivalent) before emitting color codes,
   progress bars, or interactive prompts.
3. For a hanging process, confirm it's waiting on stdin by checking
   process state, and identify which specific prompt is responsible.
4. Check whether any environment variable convention (like the widely
   recognized `NO_COLOR` or `CI` environment variables) is already
   partially supported but not consistently applied everywhere output
   formatting decisions are made.

## Fix

Check whether output is connected to an actual terminal (TTY detection)
before emitting color codes, progress bars, or any interactive-only
formatting, falling back to plain, static text output when it isn't.
Respect standard environment variable conventions (`NO_COLOR`, `CI`,
`TERM=dumb`) that scripts and CI systems commonly set to signal a
non-interactive context. For any interactive prompt, check whether stdin
is a TTY before prompting, and either fail with a clear error (if a
required input can't be obtained non-interactively) or accept a
command-line flag/environment variable as a non-interactive alternative
to the prompt, rather than hanging indefinitely.

## Pitfalls

Don't only check TTY status once at startup if the tool runs long enough
that its output destination could theoretically be reconfigured (rare,
but relevant for long-running interactive tools) -- more importantly,
don't assume `CI=true` alone is sufficient to detect every non-
interactive context; combine multiple signals (TTY check, known CI
environment variables) for robustness.

## Verify

Run the tool both interactively and piped/redirected, confirming
interactive use retains its nice formatting (colors, progress bars) while
piped/redirected use produces clean, parseable plain text with no escape
codes or hangs. Run the tool in an actual CI environment (or a
simulated non-interactive shell) to confirm no prompt causes a hang.
