---
name: namespace-package-shadowing-local-module
description: A local project file or directory accidentally shares a name with an installed package, causing Python to import the wrong one depending on the current working directory or import order.
triggers: ["local file shadowing installed package", "wrong module imported same name", "import resolves to local file not package", "module name collision python"]
permissions: ["READ"]
---

## Symptom

An `import somename` statement sometimes resolves to an installed
third-party package and sometimes to a local file or directory in the
project that happens to share the same name -- which one wins appears to
depend on the current working directory or how the script was invoked,
producing inconsistent, confusing behavior across different execution
contexts.

## Likely causes

- **A local script or module file was named the same as a popular
  installed package** (a common example: a local `types.py`, `json.py`,
  `queue.py`, or a local file named after a third-party package like
  `requests.py`), and Python's import system resolves imports based on
  `sys.path` order, which often puts the current directory or script's
  directory ahead of installed packages.
- **The current working directory is included in `sys.path`** (common
  when running a script directly rather than as an installed package/
  module), so any local file with a colliding name takes precedence
  purely because of where the script happens to be run from.
- **A namespace package (a directory without an `__init__.py`, or using
  implicit namespace package semantics) partially shares a name with an
  installed package**, creating ambiguous or unexpected merge/precedence
  behavior between the local directory and the installed package.
- **Different entry points into the codebase** (running via `python
  script.py` directly vs. `python -m package.script` vs. running through
  a test runner) have different effective `sys.path` orderings, so the
  same import statement resolves differently depending on which entry
  point was used.

## Diagnose

1. From the specific context where the wrong module is imported, run
   `python -c "import somename; print(somename.__file__)"` to see
   exactly which file was actually imported.
2. Compare that against `sys.path` order in the same context (`python -c
   "import sys; print(sys.path)"`) to understand why that particular file
   won precedence.
3. Search the project for any local file/directory with a name matching
   the colliding package.
4. Test the same import from a few different invocation contexts (direct
   script run, `-m` module run, from a different working directory) to
   confirm the inconsistency is genuinely context-dependent.

## Fix

Rename the local file/module to something that doesn't collide with an
installed package name -- this is almost always the right fix, since
fighting `sys.path` ordering to work around a naming collision is
fragile and confusing for anyone else working in the codebase later.
Prefer running the project as an installed package or module (`python -m
package.script`) rather than directly executing loose script files from
arbitrary working directories, since this produces more predictable,
consistent `sys.path` behavior across different invocation methods.

## Pitfalls

Don't try to fix a naming collision by manually reordering `sys.path` at
runtime (inserting/removing paths in code) -- that's a fragile,
non-obvious workaround that the next person modifying the code is likely
to break again; renaming the colliding local file is a permanent,
unambiguous fix.

## Verify

After renaming, run the same import from every previously-inconsistent
invocation context (direct script, `-m` module, different working
directories, test runner) and confirm it now consistently resolves to
the intended module every time, with `__file__` pointing at the expected
location in all cases.
