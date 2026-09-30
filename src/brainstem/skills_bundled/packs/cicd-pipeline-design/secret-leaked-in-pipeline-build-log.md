---
name: secret-leaked-in-pipeline-build-log
description: A secret value used in a CI/CD pipeline shows up in plaintext in the build log even though the pipeline has secret masking configured.
triggers: ["secret exposed in ci logs", "api key printed in build log", "masked secret still visible in logs", "credential leaked in pipeline output", "secret shows up unmasked in ci"]
permissions: ["READ"]
---

## Symptom
A secret (API key, database password, cloud credential) that's supposed
to be protected by the CI/CD system's secret-masking feature appears in
plaintext somewhere in a build log -- either the whole value, or enough
of it to be dangerous -- even though the secret was correctly configured
as a "secret" variable rather than a plain environment variable.

## Likely causes
1. **A step explicitly echoes or prints the variable** -- a debug
   `echo $API_KEY`, a `printenv`/`env` dump left in from troubleshooting,
   or a verbose/`-x` shell trace mode (`set -x`) that logs every command
   including ones that reference the secret as an argument.
2. **The secret is transformed before use, and masking only matches the
   original string** -- masking engines typically do literal substring
   matching on the exact registered secret value; if the pipeline
   base64-encodes it, JSON-escapes it, splits it, or interpolates it into
   a URL (`https://user:${PASSWORD}@host`), the transformed form doesn't
   match the masked pattern and prints through untouched.
3. **The secret leaks via a third-party tool's own verbose/debug output**
   rather than the pipeline's own scripted steps -- a CLI tool (cloud
   provider CLI, package manager, curl with `-v`) that echoes the full
   command line or request headers it received, including the credential
   passed as a flag or header, in its own log output which the masking
   layer wasn't applied to (e.g. output captured to a file and uploaded
   as an artifact rather than going through the console log path that
   masking hooks into).
4. **Masking is configured at the wrong scope** -- the secret is defined
   as a project/repo-level secret but referenced through an
   intermediate variable, alias, or matrix-generated name that the
   masking engine never registers as sensitive, so only the original
   variable name is protected and the copy prints freely.
5. **The secret ends up in a build artifact or cache**, not just the
   live log stream -- baked into a compiled binary's debug symbols, a
   `.env` file committed to a build cache, or an uploaded log/artifact
   file that bypasses the masking that only applies to the real-time
   console stream.

## Diagnose
- Search recent build logs (and any uploaded log artifacts, not just the
  live console view) for the secret's value or a recognizable fragment of
  it, across all steps, not just the step that's suspected.
- Read every step's script for direct references to the secret variable
  and check each one for: explicit print/echo, shell trace mode enabled,
  string transformation (encoding, concatenation, interpolation into
  another string) applied before use.
- Check whether the CLI tools invoked in the pipeline have their own
  verbose/debug flags enabled (`-v`, `--debug`, `curl -v`) that would
  independently log request details including credentials passed as
  arguments or headers.
- Confirm exactly how the secret is registered with the CI system's
  masking feature -- by which variable name, and whether every place the
  secret's value flows through the pipeline (renamed copies, matrix
  expansions, derived variables) uses that same registered name or value.

## Fix
Treat secret masking as best-effort substring matching, not a guarantee,
and design pipeline steps so the secret's raw value never needs to appear
in a loggable form: disable shell trace/verbose modes for any step that
touches a secret (`set +x` around the sensitive block, or avoid `-x`
entirely in that job), pass secrets to tools via mechanisms that don't
echo them (stdin, a temp credentials file with restricted permissions
cleaned up after, or the tool's native secret-file/credential-helper
support) rather than as visible CLI arguments, and avoid transforming a
secret's string form (encoding, concatenation) in a logged step -- do
transformations inside the target process itself where output isn't
captured. Route any third-party tool's verbose output through the same
masking-aware log sink the pipeline itself uses, or suppress that
verbosity entirely for credential-bearing calls.

## Pitfalls
- Relying solely on the platform's automatic masking and treating that as
  sufficient defense-in-depth -- once a secret has been exposed in a log
  even briefly, the correct remediation is always to rotate the secret,
  not just to fix the logging step, because logs are often retained,
  exported, or cached beyond the pipeline's own UI.
- Masking only the original registered secret string and assuming any
  transformed copy (base64-encoded, URL-embedded, concatenated) is
  automatically covered -- the fix should target the leak site (stop
  logging the transformed form) rather than expecting masking to catch
  every derived variant.
- Forgetting that uploaded build artifacts and log files are a separate
  path from the live console stream -- masking applied to the console
  view does not retroactively scrub a `.log` file already uploaded as a
  build artifact.

## Verify
After applying the fix, deliberately trigger the same code path (in a
test pipeline run with a dummy, disposable secret value) and inspect the
complete raw log output, including any uploaded log artifacts, confirming
the value is masked or entirely absent everywhere it previously appeared
-- and confirm the originally-exposed real secret has been rotated,
independent of the logging fix.
