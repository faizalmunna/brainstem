---
name: strictness-flags-not-actually-enabled
description: The team believes strict null checks and no implicit any are enforced project-wide but tsconfig, per-file overrides, or tooling gaps mean large parts of the codebase are not actually checked.
triggers: ["strictNullChecks not catching null errors", "thought we had strict mode on typescript", "noImplicitAny not working", "null undefined error slipped past typescript in production", "tsconfig strict true but still getting any"]
permissions: ["READ"]
---

## Symptom
A `null`/`undefined` runtime error (or a value silently typed `any`
somewhere) reaches production despite the team's stated belief that
`strict: true` (or `strictNullChecks`/`noImplicitAny` individually) is
enabled and should have caught exactly this class of bug at compile
time. Investigating after the fact, `tsc --noEmit` either doesn't flag
the offending code at all, or flags it only when run manually with
different flags than what CI/the editor actually uses day to day.

## Likely causes
- **`tsconfig.json` sets `strict: true` at the root, but a nested
  `tsconfig.json` in a subproject/package (common in monorepos) overrides
  it with its own, looser `compilerOptions`** that doesn't inherit or
  re-assert strictness -- TypeScript config inheritance via `extends` only
  applies if the child config actually extends the strict base; a
  sibling config authored independently (e.g. for a legacy package added
  later) can silently opt out.
- **The editor's TypeScript language service and the CI build invoke
  `tsc` with different config files or flags** (a common case: CI runs
  `tsc -p tsconfig.build.json` which excludes test files or has different
  flags than the root `tsconfig.json` the editor uses), so developers see
  strict-mode red squiggles locally that CI never actually enforces, or
  vice versa -- the team's mental model of "strict" doesn't match what's
  actually gating merges.
- **Individual files opt out via `// @ts-nocheck` at the top, or specific
  lines via `// @ts-ignore`/`// @ts-expect-error`**, added historically to
  unblock a migration or a stubborn third-party type conflict and never
  revisited -- these silence the compiler file-by-file or line-by-line
  regardless of the project-wide strictness flags.
- **`strict: true` was enabled after the codebase already existed, and
  the migration used `// @ts-ignore` comments (or a broad `skipLibCheck`/
  loosened-flags escape hatch) to get to a green build quickly**, so the
  flag is technically on but a large fraction of pre-existing files are
  individually exempted, giving a false impression of full coverage.

## Diagnose
1. Run `npx tsc --showConfig` (or `-p` pointing at the exact config CI
   uses) to print the fully-resolved effective compiler options,
   including everything inherited via `extends` -- compare this against
   what the team assumes is enabled; don't trust the root `tsconfig.json`
   file's contents alone, since `extends` chains and per-package overrides
   change the real resolved value.
2. Find every `tsconfig*.json` in the repo (`find . -name
   "tsconfig*.json"` or equivalent) and check each one's `strict`/
   `strictNullChecks`/`noImplicitAny` values independently -- a monorepo
   with N packages needs this checked N times, not once at the root.
3. Grep the whole codebase for `@ts-nocheck`, `@ts-ignore`, and
   `@ts-expect-error`, and count occurrences per top-level directory --
   a large cluster in one area is a strong signal that area was
   mechanically exempted during a strictness migration rather than
   actually fixed.
4. Diff the exact `tsc` invocation (flags, `-p` config path, working
   directory) used in the CI pipeline definition against what a developer
   runs locally or what the editor's TS server uses -- these are
   surprisingly often different commands pointed at different config
   files.

## Fix
Establish one source of truth: a root `tsconfig.base.json` with `strict:
true` (and any other desired flags) that every package/subproject config
extends via `"extends": "../../tsconfig.base.json"`, with sub-configs
only overriding `include`/`paths`/output options, never re-declaring or
loosening `compilerOptions` strictness fields. Make CI run type-checking
against the same effective config the editor uses (or explicitly document
the difference if build-time and dev-time configs must differ, e.g.
excluding test files from a production build config but still
type-checking them in a separate CI step). Address the `@ts-nocheck`/
`@ts-ignore` backlog as a tracked, incremental cleanup (file count as a
metric that should trend down) rather than leaving it as permanent
infrastructure -- each one is a specific, findable gap, not a diffuse
"someday" problem.

## Pitfalls
Don't flip `strict: true` at the root and declare the project migrated
without checking nested configs and existing suppression comments --
this produces exactly the false confidence this skill describes: the
top-level flag is honest, but real coverage is much lower. Also avoid
mass-adding `@ts-ignore` across a codebase to quickly turn on a stricter
flag for a metrics/dashboard win -- it inverts the intended effect,
making the codebase look compliant while remaining exactly as unchecked
as before in every suppressed location.

## Verify
Run `npx tsc --showConfig -p <every config file found>` and confirm
`strict`/`strictNullChecks`/`noImplicitAny` resolve to `true` in every
one, including subproject configs. Run `grep -rn "@ts-nocheck\|@ts-ignore"
` across the repo and confirm the count matches (or is below) a known,
tracked baseline rather than being an unknown, unbounded number. Finally,
confirm CI's actual type-check step invokes the same effective config by
running that exact CI command locally and comparing its error output to
what the editor shows on the same files.
