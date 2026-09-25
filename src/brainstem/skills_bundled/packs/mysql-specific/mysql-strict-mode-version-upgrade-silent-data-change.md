---
name: mysql-strict-mode-version-upgrade-silent-data-change
description: Invalid or out-of-range data that used to be silently truncated or zero-filled now causes hard INSERT/UPDATE errors after a MySQL version or sql_mode change.
triggers: ["insert suddenly failing after mysql upgrade", "data truncated for column error appearing", "sql_mode strict mode breaking inserts", "out of range value for column error", "mysql 8 upgrade insert errors"]
permissions: ["READ"]
---

## Symptom
After a MySQL/MariaDB version upgrade, or a change to the server's
`sql_mode` configuration, `INSERT`/`UPDATE` statements that previously
succeeded (often for years) start failing outright with errors like
`Data truncated for column`, `Out of range value for column`, or
`Incorrect integer value`. Alternatively, the reverse happens: data that
should have been rejected as invalid is instead silently coerced --
a string too long for a `VARCHAR` gets truncated, an out-of-range number
gets clamped to the column's min/max, or an invalid date like
`0000-00-00` gets stored as-is -- and nobody notices until a report or a
downstream job trips over the corrupted value much later.

## Likely causes
1. **A version upgrade changed the default `sql_mode`** -- MySQL 5.7
   changed the default to include `STRICT_TRANS_TABLES` (among others),
   a meaningful behavior change from 5.6's more permissive default, and
   MySQL 8.0 carries strict mode forward as default too; an application
   written and tested against an older default, or against MariaDB
   (whose defaults have historically differed from MySQL's), can start
   erroring on data patterns it silently tolerated before.
2. **`sql_mode` was explicitly changed** (in a config management update,
   a cloud provider's managed-MySQL parameter group default, or a
   well-intentioned "let's turn on strict mode for data quality") without
   auditing existing write paths for data that would now be rejected --
   flipping strict mode on is a correctness improvement in principle but
   a breaking change in practice for any code relying on the previous
   silent-coercion behavior.
3. **Application code assumes silent truncation/coercion as an implicit
   validation layer** -- e.g., relying on MySQL to truncate an
   over-length string to fit a `VARCHAR(255)` rather than validating
   length in application code first, which works until strict mode makes
   that same insert a hard error instead.
4. **Replication between a strict-mode primary and a non-strict-mode
   replica (or vice versa)**, or between a MySQL primary and a MariaDB
   replica with different effective defaults, can mean the same
   statement succeeds differently on each side, which is its own source
   of silent divergence separate from the immediate insert-error symptom.

## Diagnose
- Check the exact error message and the specific `sql_mode` value in
  effect: `SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode` -- compare
  against what was in effect before the upgrade/change (check config
  management history, parameter group revision history for managed
  databases, or the previous version's documented default).
- Identify the specific column and value that triggered the error, and
  check that column's type/length/range constraints against the actual
  data being inserted -- confirm whether this is a case of genuinely
  invalid data being correctly rejected now, versus a legitimate edge
  case (a boundary value, a locale-specific string length) that strict
  mode is newly strict about.
- Search recent write paths (ORM models, raw SQL, batch import/ETL jobs)
  for any that depend on MySQL performing silent coercion -- for example
  code that inserts unvalidated user input directly and never checks for
  truncation/rejection errors, assuming the database would "handle it."
- If this surfaced after a replication topology change, check `sql_mode`
  consistency across primary and all replicas -- a mismatch means the
  same replicated statement can be interpreted differently on each node
  (this matters most with statement-based replication; row-based
  replication ships the already-computed row values, reducing but not
  eliminating divergence risk from mode differences in application-side
  logic).

## Fix
- Treat the newly-surfaced errors as real data-quality bugs to fix at
  the source (application-level validation before the write, not
  database-level silent coercion) rather than reflexively reverting
  `sql_mode` to the permissive default -- strict mode is doing its job by
  surfacing data that was always invalid and was previously stored
  incorrectly without anyone knowing.
- Where reverting isn't immediately safe (a large legacy write path that
  can't be validated and fixed before the next deploy), scope the
  permissiveness narrowly and temporarily -- e.g., fix strict mode at the
  session level for the specific known-legacy code path while keeping
  the server default strict, with a tracked follow-up to actually fix
  the write path, rather than reverting the server-wide default
  indefinitely.
- Add application-level validation (length checks, range checks, type
  checks) before the write for any column previously relying on
  database-level coercion, so behavior doesn't depend on server
  configuration at all going forward.
- Keep `sql_mode` consistent across primary and replicas (and across
  environments -- dev/staging/production) explicitly in configuration
  management, rather than letting it drift based on each node's install
  defaults or provider defaults at the time it was provisioned.

## Pitfalls
- Reverting to a permissive `sql_mode` as a quick unblock and never
  circling back to fix the underlying data-quality gap leaves the
  database silently accepting bad data indefinitely -- the error was a
  gift (visibility into a real problem), not just an obstacle.
- Fixing `sql_mode` inconsistently across environments (e.g., strict in
  staging where it was tested, but the production change gets deployed
  separately and drifts) means a bug passes testing and still breaks in
  production, or vice versa -- masking a real issue until it's harder to
  trace.
- Assuming all now-rejected data was junk -- some legitimate edge cases
  (a boundary numeric value, a maximum-length string that was previously
  truncated by one character and "worked") can also newly fail; each
  failure needs to be individually assessed as "correctly rejected bad
  data" versus "a validation rule that's now too strict for a legitimate
  case."

## Verify
After fixing the write path (application-level validation, not
`sql_mode` reversion), replay the specific inputs that previously
triggered the error and confirm they're now either correctly rejected
with a clear application-level validation error (for genuinely invalid
data) or correctly accepted and stored exactly as provided (for
legitimate edge cases) -- and confirm `SELECT @@GLOBAL.sql_mode` matches
across primary and every replica in the topology.
