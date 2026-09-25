---
name: sast-false-positive-retriaged-every-scan
description: The same SAST finding on sanitized-safe code gets flagged and manually dismissed again on every single scan because no suppression workflow exists.
triggers: ["same false positive keeps coming back", "we dismiss this finding every scan", "sast flags sanitized input as vulnerable", "no way to mark a finding as accepted risk", "suppression annotation not working"]
permissions: ["READ"]
---

## Symptom
A SAST tool flags a genuinely risky-looking pattern -- string
concatenation into a SQL query, a `subprocess` call built from a
variable -- in a spot where the input is actually validated or
parameterized safely a few lines away or in a wrapper the analyzer
doesn't trace into. A human reviewer correctly determines it's a false
positive once, but because there's no durable suppression mechanism (or
nobody knows the tool has one), the exact same finding reappears and
gets manually re-reviewed and re-dismissed on every subsequent scan,
forever.

## Likely causes
1. **The tool's dataflow analysis has a real, structural blind spot** --
   it can't trace taint through the specific sanitization function used
   (a custom validator, an ORM's parameterization layer, a wrapper
   around a safe API), so it will flag this exact call site every time
   no matter how many times it's reviewed, because the underlying
   analysis limitation hasn't changed.
2. **Dismissals are recorded somewhere transient** -- a comment in a
   Slack thread, a checkbox in the SAST vendor's web dashboard that
   isn't tied to the commit/line, or a verbal "yeah that's fine" --
   instead of a suppression artifact that lives with the code and
   survives the next scan.
3. **The suppression mechanism exists but isn't in the CI-invoked
   config** -- inline suppression comments or a baseline file were added
   locally but never committed, or the CI job runs the scanner without
   pointing at the suppression/baseline file the local run uses.
4. **Suppressions are scoped too broadly or too narrowly to survive
   refactors** -- a suppression tied to an exact line number breaks the
   moment the file is reformatted or a line is added above it, silently
   reverting to "unsuppressed" without anyone deciding that.

## Diagnose
- Check whether the finding's line/hash is stable across scans -- if the
  SAST tool assigns a stable fingerprint (many do, e.g. a hash of rule +
  normalized code snippet) note whether that fingerprint appears in any
  suppression/baseline file already, versus not being tracked anywhere.
- Read the tool's actual dataflow trace for this finding (most SAST
  tools show the source-to-sink path) to confirm whether the
  sanitization step is genuinely outside what the tool's taint analysis
  can follow (a real, permanent limitation) versus the tool simply not
  having been given a chance to see it (e.g. sanitizer defined in a
  file/module excluded from the scan).
- Search the repo for any existing suppression syntax the tool supports
  (`# nosemgrep`, `// NOSONAR`, CodeQL `.codeqlignore`, a
  `.checkmarx-baseline.json`) to check whether one was already added but
  not wired into CI, versus never attempted.
- Confirm the CI scan invocation's exact command/config against the
  local one used when the finding was reviewed -- a mismatched config
  path is a common reason a suppression "doesn't work" in CI despite
  working locally.

## Fix
Use the tool's durable, code-adjacent suppression mechanism -- an inline
suppression comment on the flagged line with a required justification
and ticket/reference (most tools support `# nosemgrep: rule-id --
reason`-style annotations, not bare suppressions) or a committed
baseline/suppression file keyed by stable finding fingerprint rather
than line number -- and require the justification to state *why* it's
safe (e.g. "parameterized via ORM `.filter()`, not raw SQL") so a future
reviewer can validate the reasoning still holds rather than re-deriving
it from scratch. Commit the suppression alongside the code change it
applies to, in the same PR, so it's reviewed by the same people
approving the code, and confirm the CI scan invocation actually loads
that suppression source (test it in a branch before relying on it).

## Pitfalls
- Suppressing at the rule level repo-wide (disabling the SQL-injection
  rule entirely) to silence one false positive throws away detection for
  every genuine future instance of that rule -- suppress the specific
  finding/call site, not the rule class.
- A suppression with no reason/justification field ("just make it stop")
  is indistinguishable from a real vulnerability being hidden six
  months later when nobody remembers why it was dismissed -- always
  require and review the stated reasoning.
- Suppressing by line number instead of a stable content/AST-based
  fingerprint silently expires the suppression on the next unrelated
  edit to that file, causing the exact "re-triaged every scan" symptom
  to resurface intermittently rather than being fixed.

## Verify
Re-run the scan twice across two commits that touch unrelated lines in
the same file and confirm the suppressed finding does not reappear in
either run, then intentionally modify the sanitization logic at the
suppressed call site (e.g. temporarily remove the parameterization) and
confirm the finding *does* reappear -- proving the suppression is scoped
to the safe pattern specifically, not blindly hiding the whole rule/file.
