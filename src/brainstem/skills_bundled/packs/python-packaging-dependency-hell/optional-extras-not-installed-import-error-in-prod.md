---
name: optional-extras-not-installed-import-error-in-prod
description: A feature works in development but fails in production with an ImportError because it depends on an optional package extra that wasn't included in the production install command.
triggers: ["importerror works locally fails production", "optional extra not installed production", "missing optional dependency deployed app", "pip install extras not included in deploy"]
permissions: ["READ"]
---

## Symptom

A feature that works correctly in local development fails in production
(or any environment set up independently) with an `ImportError` or
`ModuleNotFoundError` for a package that's genuinely listed as a
dependency somewhere in the project's configuration -- but the specific
install command used for that environment didn't include the "extra"
that package belongs to.

## Likely causes

- **The package is declared as an optional extra**
  (`package[extra_name]` syntax, or an equivalent "optional-dependencies"
  group) in `pyproject.toml`/`setup.py`, and the production install
  command installs the base package without specifying that extra, while
  a developer's local setup happened to include it (perhaps via a
  broader "install everything" habit, or an editable install that
  included dev/all extras).
- **A new feature was added that depends on a package belonging to an
  existing extra group**, but the deployment configuration's install
  command wasn't updated to include that extra, since it was already
  working before this specific feature was added.
- **Different environments use different install commands entirely**
  (a `requirements-dev.txt` for local development that includes
  everything, versus a minimal `requirements.txt` for production), and
  the two were allowed to drift out of sync regarding which extras are
  actually needed for which environment.
- **The extra was added correctly to the relevant configuration, but the
  deployment pipeline caches or reuses a previously-built environment**
  that predates the extra being added, and the cache wasn't invalidated.

## Diagnose

1. Confirm the exact package/module causing the `ImportError` and
   identify which extra group it belongs to in the project's dependency
   configuration.
2. Compare the exact install command used in the failing environment
   against the one used in the working (development) environment, looking
   specifically for extras specification differences.
3. Check whether the feature using this dependency was recently added,
   and whether the corresponding extras declaration was updated at the
   same time as the feature code.
4. If a build/deployment cache is suspected, check cache invalidation
   logic against when the extras configuration actually changed.

## Fix

Update the production (or any environment-specific) install command to
include the required extra, matching what the feature actually needs.
Where practical, reduce the number of distinct install-command variants
across environments (development, CI, production) to minimize the
chance of drift, or explicitly document and test that each environment's
install command is verified against actual current requirements as part
of the deployment/CI process. If a build cache is involved, ensure it's
correctly keyed on the dependency configuration so a change to extras
invalidates it.

## Pitfalls

Don't respond by simply moving the dependency out of an optional extra
and into the base/required dependencies to avoid ever hitting this again
-- if the dependency is genuinely optional for some legitimate use cases
(a heavy dependency not everyone needs), that removes a real, intentional
distinction; fix the specific environment's install command instead of
eliminating the optionality.

## Verify

Rebuild the previously-failing environment from scratch using the
corrected install command and confirm the feature now works without the
import error. Add an automated check (a CI step that installs using each
environment's actual documented command and imports the relevant
modules) so a future extras/feature mismatch is caught before deployment
rather than discovered in production.
