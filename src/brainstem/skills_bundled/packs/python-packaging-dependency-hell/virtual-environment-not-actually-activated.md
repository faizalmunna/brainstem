---
name: virtual-environment-not-actually-activated
description: Python packages install successfully but the application still can't import them, or imports an unexpected version, because commands are running against a different Python interpreter than the intended virtual environment.
triggers: ["module not found despite pip install", "wrong python version being used", "virtualenv not active but seems fine", "pip installed into wrong environment"]
permissions: ["READ"]
---

## Symptom

`pip install somepackage` reports success, but running the application
(or even just `python -c "import somepackage"`) fails with
`ModuleNotFoundError`, or imports a different, unexpected version of a
package than what was just installed -- the install and the run are
silently happening against two different Python environments.

## Likely causes

- **The virtual environment wasn't actually activated in the current
  shell session** where the install command was run, so `pip install`
  installed into the system/global Python (or a different environment
  entirely) rather than the intended project virtual environment.
- **Multiple Python installations exist on the machine** (a system
  Python, a pyenv-managed version, a Homebrew-installed version, a
  virtual environment), and `python`/`pip` on `PATH` resolves to a
  different one than intended, especially after a shell configuration
  change or in a fresh terminal session that didn't source the expected
  activation script.
- **An IDE or editor's configured Python interpreter differs from the
  one used in a terminal**, so code run through the IDE's "run" button
  uses a different environment than manual terminal commands, producing
  inconsistent behavior depending on how the code is executed.
- **A tool invoked via `sudo` or a different user context loses the
  active virtual environment's `PATH` modifications**, silently falling
  back to a system-level Python/pip.

## Diagnose

1. Run `which python` and `which pip` (or the Windows equivalent) in the
   exact shell/context where the failure occurs, and compare the
   resolved paths against the expected virtual environment's directory.
2. Run `python -m pip show <package>` (rather than assuming a global
   `pip show`) to confirm which interpreter's site-packages the
   currently-active `python` command would actually import from.
3. Check the IDE/editor's configured interpreter path against the
   terminal's active environment if the discrepancy only appears in one
   context.
4. Check shell startup scripts/profile configuration for whether virtual
   environment activation is expected to happen automatically and
   whether it's actually happening in the specific session experiencing
   the issue.

## Fix

Always run `python -m pip install ...` rather than bare `pip install
...`, since this guarantees the install target is whatever `python`
itself currently resolves to, making the relationship between "what
installs" and "what runs" explicit and consistent rather than relying on
`pip` and `python` happening to point at the same place. Explicitly
verify and align the IDE/editor's configured interpreter with the
terminal's intended virtual environment. For automation/CI, activate the
virtual environment explicitly and verify (`which python`) as an early,
visible step rather than assuming activation succeeded silently.

## Pitfalls

Don't work around interpreter confusion by installing packages globally
(outside any virtual environment) "to make sure they're available
everywhere" -- that reintroduces exactly the dependency-isolation
problems virtual environments exist to prevent, and can create version
conflicts between unrelated projects sharing the same global Python
installation.

## Verify

From the exact context where the application actually runs (the real
terminal session, the real IDE run configuration, the real CI job step),
run `python -m pip show <package>` for the specific package in question
and confirm it resolves to the expected virtual environment's
site-packages location with the expected version.
