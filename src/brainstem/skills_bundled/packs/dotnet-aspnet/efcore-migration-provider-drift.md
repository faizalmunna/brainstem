---
name: efcore-migration-provider-drift
description: Diagnose an EF Core migration that produces different schema behavior in production than in local development due to provider-specific defaults.
triggers: ["migration works locally fails in production", "decimal precision truncated in production db", "datetime kind mismatch sql server", "sqlite migration doesn't match sql server behavior", "column default differs between environments"]
permissions: ["READ"]
---

## Symptom
A migration applies cleanly in both local development and production,
but the resulting data or query behavior differs between them --
common manifestations: decimal values silently truncated/rounded in one
environment, a `DateTime` column that's timezone-sensitive in one
provider but not another, a string comparison that's case-sensitive in
production but wasn't locally, or a column default value/constraint that
exists in one database but not the other despite both having "run all
migrations." No migration failure is reported; the schema and/or data
behavior is just quietly wrong in one environment.

## Likely causes
1. **Developing against SQLite (or another lightweight provider) locally
   while production runs SQL Server/PostgreSQL/MySQL** -- these providers
   have materially different default behaviors for the same EF Core model
   (e.g. SQLite is dynamically typed and forgiving about type mismatches
   that SQL Server enforces strictly; collation/case-sensitivity defaults
   differ between SQL Server, PostgreSQL, and MySQL), so a migration and
   model that "work" locally can behave differently once applied against
   the real production provider.
2. **No explicit precision/scale specified on `decimal` properties** --
   EF Core's default decimal mapping varies by provider and version
   (historically SQL Server defaulted to `decimal(18,2)`, silently
   truncating values with more decimal places, while other providers or
   versions may differ), so values that round-trip fine in one provider
   silently lose precision in another unless `[Column(TypeName =
   "decimal(18,4)")]` or `HasPrecision()` is set explicitly in
   `OnModelCreating`.
3. **A `DateTime` (vs `DateTimeOffset`) column's timezone handling
   depends on provider and server configuration** -- SQL Server's
   `datetime2` has no timezone awareness at all, so `DateTime.UtcNow`
   values behave correctly only as long as every writer is consistent;
   switching providers, or having one environment's server default to
   local time and another to UTC, produces data that's silently offset
   rather than erroring.
4. **A migration was generated against one provider's design-time
   snapshot but applied against a database that was manually altered out
   of band** (a DBA changed a default/index directly in production, or a
   previous migration was applied manually instead of through EF's
   migration history), so the migration history table
   (`__EFMigrationsHistory`) says the schema matches the model when it
   doesn't -- the drift isn't from the provider at all but from schema
   changes EF never tracked.

## Diagnose
- Compare `dotnet ef migrations script` output generated against the
  actual production provider (not just the local dev provider) --
  generate the idempotent SQL script for each provider EF is configured
  to target and diff it, rather than assuming the same migration produces
  identical SQL everywhere.
- Grep the model configuration (`OnModelCreating`, entity configuration
  classes, and data annotations) for `decimal` properties missing an
  explicit `HasPrecision()`/`HasColumnType()`, and for `DateTime`
  properties without a documented UTC-vs-local convention enforced (e.g.
  a `SaveChanges` interceptor that normalizes to UTC).
- Query production's actual column definitions
  (`INFORMATION_SCHEMA.COLUMNS` or the provider equivalent) and diff them
  against what the current EF model expects -- a mismatch here that
  migrations don't explain confirms manual/out-of-band schema drift
  rather than a provider-default issue.
- Check `__EFMigrationsHistory` in production against the local
  migrations folder -- confirm every migration file has a corresponding
  applied row and there are no gaps, which would indicate a migration was
  skipped or manually reconciled.
- If a case-sensitivity or collation difference is suspected, run the
  same query with a value differing only in case against both
  environments and compare row counts returned.

## Fix
- Develop and run integration tests against the same database engine
  used in production (e.g. a containerized SQL Server/PostgreSQL instance
  in CI and locally via Testcontainers or Docker Compose) rather than a
  lightweight stand-in provider, so provider-specific behavior surfaces
  before deployment, not after.
- Make precision, scale, and column types explicit in the model for every
  `decimal` and any type with provider-dependent defaults, using
  `HasPrecision()`/`HasColumnType()` in `OnModelCreating` (or a shared
  base configuration applied via `IEntityTypeConfiguration<T>`), so the
  generated migration is explicit rather than relying on a provider
  default that can change between versions or differ across providers.
- Standardize on UTC everywhere: store `DateTime` values as UTC
  consistently (or use `DateTimeOffset` where timezone information must
  be preserved), and enforce it centrally with a `SaveChanges`
  interceptor or value converter rather than trusting every call site to
  remember `.ToUniversalTime()`.
- Reconcile out-of-band schema drift by generating a migration from the
  current model and diffing its SQL against production's actual schema;
  if production was altered manually, either codify that change as a
  proper migration (possibly an empty migration with the equivalent SQL,
  marked as already applied if it's already live) or revert the manual
  change so the migration history is trustworthy again.

## Pitfalls
- Fixing the immediate precision/date bug without switching CI/local dev
  to the same provider as production leaves the underlying gap open --
  the next schema change can reintroduce a different provider-specific
  drift that won't be caught until it's already in production again.
- Applying a "corrective" migration directly to production via manual SQL
  to fix drift, without also updating the EF model and migration history
  to match, recreates the exact same drift-vs-migration-history mismatch
  that caused the problem, just with a different schema underneath it.

## Verify
Run `dotnet ef migrations script` against a database matching the
production provider and version, apply it to a fresh instance seeded
with representative data (including edge-case decimal values and
non-UTC-looking datetimes), and confirm the resulting stored values and
query results match what production actually returns for the same
inputs -- not just that the migration applies without error.
