---
name: mysql-utf8-vs-utf8mb4-truncation
description: Emoji or other 4-byte Unicode characters fail to insert or get silently truncated because a column or connection is still using MySQL's legacy utf8 charset.
triggers: ["incorrect string value error emoji", "emoji breaking insert mysql", "utf8 vs utf8mb4 mysql", "4 byte character truncation", "text cut off after emoji mysql"]
permissions: ["READ"]
---

## Symptom
Inserting text containing emoji, certain CJK extension characters, or
other characters outside the Basic Multilingual Plane either fails
outright with `Incorrect string value: '\xF0\x9F...' for column`, or
succeeds but silently truncates the string at the offending character
(everything after the emoji is missing), or stores a mangled/replacement
character instead of the original content. This often surfaces only
after a feature ships that lets users type free-form text (a comment,
a display name, a chat message) since earlier test data rarely included
emoji or rare CJK characters.

## Likely causes
1. **The column (or table/database default) is defined as MySQL's
   legacy `utf8` charset, which is actually a 3-byte-max encoding
   (`utf8mb3` in modern MySQL's own naming), not full Unicode UTF-8** --
   it cannot represent any character requiring 4 bytes, which includes
   most emoji, some CJK extension characters, and mathematical symbols,
   so a value MySQL calls "utf8" is a historically confusing misnomer
   that isn't actually complete UTF-8 support.
2. **The column is correctly `utf8mb4`, but the connection charset
   negotiated by the client library defaults to `utf8` (3-byte)** --
   the table-level definition is right, but the driver/ORM's connection
   settings silently downgrade what's sent/received, so 4-byte characters
   are mangled or rejected in transit even though the schema could store
   them.
3. **A schema was created years ago under an older MySQL default (`utf8`/
   `latin1` was the historical default charset in older MySQL versions)
   and never migrated when the application's stack moved to assuming
   full Unicode support** -- the mismatch between "what the app assumes"
   and "what the schema actually declares" goes unnoticed until real
   user input exercises it.
4. **Only some columns/tables were migrated to `utf8mb4`** during a
   partial past migration effort, so the failure is inconsistent --
   works on the users table, fails on the comments table -- which makes
   it look like a code bug rather than a schema-consistency gap.
5. **Index length limits under `utf8mb4` versus `utf8`** -- because
   `utf8mb4` uses up to 4 bytes per character versus 3 for `utf8`, a
   `VARCHAR` column near the max indexable length under the old charset
   can exceed the max index key length after converting to `utf8mb4`
   (particularly relevant on `innodb_large_prefix`-sensitive older
   configurations), causing the migration itself to fail with an index
   key too long error rather than the original truncation symptom.

## Diagnose
- Check the actual column and table charset:
  `SHOW CREATE TABLE <table>` (look at each column's `CHARACTER SET`
  and the table's `DEFAULT CHARSET`), and
  `SELECT character_set_name FROM information_schema.columns WHERE
  table_name = '<table>' AND column_name = '<column>'` for precision --
  confirm whether it's `utf8mb4` or the legacy `utf8`/`utf8mb3`.
- Check the connection-level charset the application is actually using
  at write time: `SHOW VARIABLES LIKE 'character_set_connection'` for
  the session in question, or the driver/ORM's configured connection
  charset parameter (e.g., a DSN string missing `charset=utf8mb4`
  defaults to the driver's own default, which is frequently `utf8`, not
  `utf8mb4`).
- Reproduce directly: attempt to insert a known 4-byte character (an
  emoji, or `SELECT HEX(CONVERT(x'F09F9880' USING utf8mb4))` as a
  controlled test) through the exact same code path (same driver,
  same connection config) that's failing in production, isolating
  whether the problem is schema, connection, or both.
- If migrating, check for any index whose byte length under `utf8mb4`
  (4 bytes/char max) would exceed the storage engine's max key length,
  which would make a straightforward `ALTER TABLE ... CONVERT TO
  CHARACTER SET utf8mb4` fail on that specific index rather than
  succeed silently.

## Fix
- Convert affected columns/tables (and ideally the database default) to
  `utf8mb4` with an appropriate collation (`utf8mb4_unicode_ci` or
  `utf8mb4_0900_ai_ci` on MySQL 8, matching whatever collation semantics
  the application needs) via `ALTER TABLE ... CONVERT TO CHARACTER SET
  utf8mb4`, checking index length constraints first so the migration
  doesn't fail partway through on a specific table.
- Explicitly set the connection charset to `utf8mb4` in the
  driver/ORM/DSN configuration (not just relying on the schema default),
  since a correct schema with a wrong connection charset still mangles
  data in transit -- both layers need to agree.
- Audit all tables/columns for consistency rather than fixing only the
  one that surfaced the bug report -- a partial migration reproduces the
  same failure mode on the next table that happens to receive emoji
  input, just later.
- For any index that would exceed max key length after converting to
  `utf8mb4`, either shorten the indexed prefix length explicitly
  (`ALTER TABLE ... ADD INDEX (col(191))` accounts for the worst case
  4-byte-per-char length within common key-length limits) or reduce the
  column's max length if the business data doesn't actually need it.

## Pitfalls
- Converting the column's charset without also fixing the connection
  charset (or vice versa) leaves the bug partially fixed -- both must be
  `utf8mb4` for correct end-to-end behavior, and testing only at the
  schema level can miss a connection-level mismatch.
- Running the charset conversion on a large table without accounting for
  the fact that `ALTER TABLE ... CONVERT TO CHARACTER SET` rewrites
  every row and can be a long-running, table-rebuilding operation --
  treat it with the same care (online schema-change tooling, off-peak
  timing, replica lag monitoring) as any other large ALTER, not as a
  quick metadata-only change.
- Assuming existing data that was silently truncated before the fix will
  retroactively repair itself -- it won't; already-truncated/mangled
  rows need their own data-correction pass (from an application-level
  source of truth, a backup, or accepting the loss), separate from
  preventing new truncation going forward.

## Verify
After conversion, insert a test string containing a known 4-byte
character (a common emoji) through the actual application code path
(not just a raw SQL client) and confirm via `SELECT HEX(column)` or
direct display that the character round-trips intact, with no
truncation of trailing content and no replacement/mangled character; run
this check against every table that accepts free-form user text, not
just the one that originally surfaced the bug.
