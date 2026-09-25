---
name: typosquatted-package-installed-by-misspelling
description: A commonly misspelled package name gets installed instead of the intended popular library due to a typo in an install command or manifest.
triggers: ["installed the wrong package by typo", "pip install typo installed malicious package", "package name looks almost identical to the real one", "typosquatting on npm or pypi", "someone fat-fingered a package install command"]
permissions: ["READ"]
---

## Symptom
A developer runs an install command or adds a dependency to a manifest
file with a small typo (a transposed letter, missing hyphen, wrong
pluralization) in an otherwise well-known, popular package name, and the
command succeeds without error because a different package -- registered
under exactly that misspelled name -- actually exists on the registry and
gets installed instead. The mistake is often only caught later, if at all,
when the package behaves unexpectedly or a security scan flags it, because
the install itself gave no indication anything was wrong.

## Likely causes
1. **A manual, one-off install command was typed from memory** (e.g. in a
   terminal, a quick script, or a Dockerfile `RUN pip install ...` line)
   without copy-pasting the exact name from the official source, and
   autocomplete/spellcheck isn't available in that context.
2. **The manifest file itself has the typo** (a hand-edited
   `package.json`, `requirements.txt`, or `pom.xml`) and it went unnoticed
   through code review because the misspelled name is visually close
   enough to the real one that reviewers pattern-match it as correct.
3. **The registry allows squatting on common misspellings of popular
   package names** with no automatic detection or warning at install time
   -- most package managers install whatever name resolves without any
   "did you mean" check, unlike a search engine.
4. **A tutorial, blog post, AI-generated snippet, or outdated internal
   doc contains the typo already**, and it gets copy-pasted verbatim by
   someone who has no reason to doubt a source that otherwise looks
   authoritative.

## Diagnose
- For every dependency in the manifest, compare the exact name character-
  by-character against the package's official name as listed on its
  official documentation site or canonical GitHub repo -- don't rely on
  visual skimming; a scripted diff against a known-good list of intended
  package names catches transpositions a human eye skips over.
- Check the suspect package's registry page for signals of typosquatting:
  a description that mimics the real package's but with poor quality or
  no real functionality, a first-publish date far more recent than the
  real package, and a download count far lower than what the real,
  popular package would have.
- Check install logs / CI build logs for the literal resolved package
  name and version that was fetched -- confirming what was actually
  installed, not just what's declared in the manifest, catches cases
  where the manifest itself is correct but a stray manual install
  elsewhere in a Dockerfile or setup script introduced the typo.
- If the misspelled package was actually installed and used, check
  whether the application still functions -- a typosquat with no real
  functionality will typically throw import/require errors immediately,
  while a more sophisticated one may proxy through to the real package
  after executing malicious code, making the mistake much harder to
  notice from behavior alone.

## Fix
Correct the manifest entry to the exact official package name and
version, then remove the malicious package from the lockfile and any
cached build layers so it can't be silently reintroduced. Add an
automated check to CI that validates dependency names against an
allowlist or against the officially published name for well-known
libraries the team uses (many ecosystems have community-maintained
typosquat-detection tools, or a simple Levenshtein-distance check against
a curated list of the team's actual intended top-level dependencies is
enough to catch most cases). For manual installs in Dockerfiles or setup
scripts, prefer generating the install command from the already-reviewed
manifest file rather than typing package names inline a second time, so
there's only one place a typo could occur and it's the one already
protected by review and CI validation.

## Pitfalls
- Fixing the immediate typo without checking whether the malicious
  package's install scripts already executed -- by the time the mistake
  is noticed, any `postinstall` payload may have already run and accessed
  the environment's secrets, so credential rotation may still be needed
  even for a "caught quickly" typo.
- Trusting code review to catch this reliably -- typosquat names are
  specifically chosen to be visually similar, and review is not a
  substitute for an automated name-validation check that doesn't rely on
  human pattern matching.
- Only checking the top-level manifest for typos and not manual install
  commands embedded in Dockerfiles, Makefiles, or onboarding scripts,
  where the same mistake can be introduced outside the reviewed
  dependency file entirely.

## Verify
Re-run the install from a clean environment and confirm the resolved
package name in the lockfile and install log exactly matches the intended
official package, character for character. Confirm the malicious package
is absent from the lockfile, any Docker image layers, and build caches by
grepping for its exact (misspelled) name. Confirm the automated name-
validation check actually fails when given the known-bad misspelled name,
so the guard is proven to catch a repeat, not just assumed to work.
