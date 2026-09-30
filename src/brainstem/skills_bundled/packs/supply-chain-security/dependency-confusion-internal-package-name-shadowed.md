---
name: dependency-confusion-internal-package-name-shadowed
description: A build pulls a malicious public package instead of the intended internal one because an attacker published the same name publicly with a higher version.
triggers: ["build installed the wrong version of our internal package", "internal package name also exists on public npm registry", "dependency confusion attack", "private package pulled from public registry instead of internal", "unscoped internal package name collision"]
permissions: ["READ"]
---

## Symptom
A build or CI pipeline installs a package that looks like the team's own
internal/private package (same name, e.g. `company-auth-utils`) but the
code that ends up running isn't the internal one -- it executes unexpected
logic, phones home to an unfamiliar domain, or a security review discovers
the installed package's contents don't match the internal repo at all. The
package resolved from the public registry (npm, PyPI) rather than from the
internal/private registry, even though a private version of the same name
exists.

## Likely causes
1. **The internal package name was never reserved on the public registry**,
   and an attacker registered that exact name publicly with a version
   number higher than the internal package's current version -- most
   package managers' default resolution order prefers the highest
   available version across configured registries unless explicitly told
   to scope or prioritize the private one.
2. **The package manager config doesn't pin/scope internal package names
   to the private registry** -- e.g. no `.npmrc` scope mapping, no pip
   `--index-url` restriction, so a plain `npm install`/`pip install` is
   free to check the public registry and finds a "newer" match there.
3. **CI runners use a different, more permissive package-manager
   configuration than developer machines** (a fresh container without the
   `.npmrc`/`pip.conf` that developers have locally), so the vulnerability
   is invisible in local dev and only triggers in CI/production builds.
4. **The internal package name was chosen without a registry-reserved
   namespace/scope** (e.g. an unscoped npm name instead of `@company/`),
   leaving it fully open to public registration by anyone.

## Diagnose
- For any internal package name, check whether that exact name already
  exists on the relevant public registry (`npm view <name>`,
  `pip index versions <name>`) -- if it does and it's not owned by the
  organization, dependency confusion is possible right now, not just
  hypothetically.
- Inspect the package-manager configuration actually used by CI (not just
  what's in a developer's local config) -- check `.npmrc`/`pip.conf`/
  `NuGet.config` inside the CI job's actual runtime environment for
  registry scoping rules, since a config file present in the repo isn't
  proof it's honored by every runner image.
- Check installed package provenance after a build: compare the installed
  package's file hash/contents against the internal package's expected
  source -- a mismatch confirms the wrong one resolved, and checking the
  install log for which registry URL actually served the package confirms
  the exact resolution path.
- Check whether the internal package's version number in the private
  registry is lower than any public-registry package of the same name --
  this is the most common trigger condition since most resolvers pick the
  highest semver-satisfying version by default.

## Fix
Reserve the exact internal package name(s) on the public registry as
empty placeholder packages the organization controls, even if never
published with real code, so an attacker cannot register them. In
parallel, use scoped package names for anything internal (`@company/name`
on npm, a reserved prefix on PyPI) since scopes/prefixes tied to a
verified organization cannot be squatted by unrelated accounts. Configure
the package manager explicitly to only resolve internal package names (or
the whole scope) from the private registry -- npm's scoped registry
mapping in `.npmrc`, or pip's `--index-url`/`--extra-index-url` ordering
combined with per-package pinning where the tooling supports it -- and
apply that configuration inside the CI environment itself, verified
independently of what's checked into the repo, since a config file that
isn't actually loaded by the runner provides no protection.

## Pitfalls
- Relying on "our internal package has a higher version number than
  anything public" as the defense -- an attacker who notices the internal
  name can simply publish a higher version publicly at any time; version
  ordering is not a security boundary.
- Fixing the `.npmrc` in the source repo but not confirming CI runners
  actually load it -- a fresh, ephemeral CI container that doesn't mount
  or copy the same config file will still be vulnerable even after the
  "fix" is merged.
- Using scoped names for new internal packages going forward while
  leaving older, already-shipped unscoped internal package names
  unprotected -- the confusion risk applies per package name, and
  legacy names need the same registry-reservation treatment.

## Verify
Confirm resolution by running the exact install command CI uses in a
clean, matching environment and checking the install log's reported
source registry URL for the internal package name -- it must show the
private registry, not the public one. Confirm the placeholder/reservation
by checking that the public registry page for the internal package name
(if reserved) shows the organization's placeholder, not a third-party
publisher. Recheck after any CI runner image or base container update,
since registry configuration can silently reset when base images change.
