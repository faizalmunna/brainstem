---
name: serialized-column-loses-type-after-reload
description: Fix a serialized or JSON ActiveRecord column that returns different Ruby types after being saved and read back than before it was saved.
triggers: ["json column returns strings instead of symbols", "serialized column type changes after reload", "activerecord store loses hash keys as strings", "jsonb column value wrong type after save", "serialize attribute round trip bug"]
permissions: ["READ"]
---

## Symptom
Code writes a value into a `serialize`d or JSON/JSONB column (a hash with
symbol keys, a value containing a `Time`/`Date`, a value that's `nil` vs.
an empty hash) and everything works fine using the in-memory object right
after assignment -- but after the record is saved and re-read (a fresh
`find`, a different request, or after `reload`), the same data comes back
with different types: symbol keys became strings, a `Time` became a
plain string, or a previously-`nil` field is now an empty hash/array, and
code that does `hash[:key]` or `value.is_a?(Time)` downstream breaks.

## Likely causes
1. **JSON has no native symbol or Time type** -- serializing to JSON
   (`serialize :data, JSON` or a native `jsonb`/`json` column) always
   round-trips symbol keys as strings and `Time`/`Date`/`DateTime` objects
   as ISO8601 strings, because that's what the JSON format itself
   supports; code written and tested only against the pre-save in-memory
   object never notices until it reads a *reloaded* record.
2. **`serialize :column, Hash` (the older, non-JSON serializer, using
   YAML by default) behaves differently from `serialize :column, JSON`**
   -- YAML *does* preserve Ruby-specific types like symbols, but a
   migration from one serializer to the other (or a mixed codebase where
   some rows were written under the old serializer and some under the
   new one) leaves existing rows in a format the current serializer
   can't correctly parse back into the expected shape.
3. **`store_accessor`/`ActiveRecord::Store` on a JSON column defines
   convenient reader methods, but direct hash access
   (`record.data["key"]` vs `record.data[:key]`) is used inconsistently**
   across the codebase, so some code paths "work" only because they
   happen to use the accessor while others break by reaching into the
   raw hash with the wrong key type.
4. **A `nil` value written to the column is coerced to an empty
   hash/array by a default (`default: {}` on the column, or `after_initialize`
   logic), so code checking `column.nil?` to distinguish "never set" from
   "explicitly emptied" gets the wrong answer after a reload**, even
   though it worked pre-save when the in-memory object still held the
   literal `nil` that was assigned.

## Diagnose
- In a console, assign the value, call `record.save!`, then call
  `record.reload` (critically, not just re-reading the in-memory object)
  and inspect the value's actual class
  (`record.data.class`, `record.data.keys.first.class`) -- compare
  against what it was immediately after assignment, before saving.
- Check the migration/schema for the column's actual database type
  (`json`, `jsonb`, `text` with a `serialize` call) and check the model
  for exactly which serializer/coder is configured
  (`serialize :data, JSON`, `serialize :data, Hash`, or nothing -- native
  `jsonb` handled by the adapter directly).
- If `serialize` was changed at some point (check git blame/history on
  that model line), query a few existing rows' raw column content
  directly via SQL (bypassing ActiveRecord's coder) to see whether older
  rows are stored in a different format (YAML vs JSON) than new writes.
- Grep the codebase for both symbol-key and string-key access on the same
  column (`record.data[:foo]` vs `record.data["foo"]`) across different
  files -- inconsistent access patterns are the direct symptom of relying
  on pre-save object identity rather than the actual persisted shape.

## Fix
- Treat the column's persisted shape (string keys, string-formatted
  timestamps if using JSON) as the source of truth everywhere, including
  right after assignment -- use `HashWithIndifferentAccess`
  (`record.data = ActiveSupport::HashWithIndifferentAccess.new(...)`, or
  configure the JSON coder to always return one) so `[:key]` and
  `["key"]` both work consistently whether or not the record has been
  reloaded.
- If Time/Date values must round-trip through a JSON column, explicitly
  parse them back on read (a custom `ActiveRecord::Type` or an explicit
  `Time.parse` at the point of use) rather than assuming the stored
  string is usable as-is -- don't rely on implicit coercion.
- When migrating a column from `serialize :column, Hash` (YAML) to a
  native `jsonb` column or `serialize :column, JSON`, write a one-time
  data migration that reads every existing row under the *old* coder and
  rewrites it under the *new* one, rather than switching the model's
  declared serializer and assuming old rows will still parse correctly.
- Be explicit about the `nil`-vs-empty distinction: if "never set" must be
  distinguishable from "explicitly emptied," don't give the column a
  non-nil default; instead handle the default in application logic where
  the distinction can be preserved, or add a separate boolean/sentinel
  rather than overloading the same column for both meanings.

## Pitfalls
- Writing tests that only check the in-memory object immediately after
  assignment (never calling `reload` or re-fetching from the database)
  will pass even when this bug is present -- any test covering a
  serialized/JSON column's round-trip behavior must reload the record.
- Wrapping every read site in ad hoc `.symbolize_keys` calls patches
  individual call sites but leaves the underlying inconsistency in place
  for the next new call site -- fix it once at the type/coder level
  (custom `ActiveRecord::Type`, or consistently using
  `HashWithIndifferentAccess`) instead of scattering defensive calls.
- Assuming a Rails/database upgrade that changes the default column type
  (e.g. `json` to `jsonb`, or a serializer default changing across major
  Rails versions) is purely a performance change -- check whether it also
  changes round-trip type behavior for existing data.

## Verify
In a test, assign a value to the column that exercises the specific type
concern (symbol keys, a Time value, or an explicit `nil`), save the
record, call `.reload` (not just re-read the in-memory variable), and
assert the reloaded value's type and key format match what the rest of
the codebase actually expects -- not what was true immediately after
assignment.
