---
name: sql-injection-prevention
description: Diagnose and fix SQL injection vulnerabilities from string-built queries, and verify parameterization actually closes the hole.
triggers: ["sql injection", "sqli", "string concatenation sql", "raw sql query user input", "sanitize sql input"]
permissions: ["READ"]
---

## Symptom
User-controllable input reaches a SQL query via string concatenation or
formatting (`f"SELECT * FROM users WHERE id = {user_id}"`,
`"..." + request.params.name + "..."`), letting an attacker alter the
query's structure -- extract other users' data, bypass authentication, or
modify/delete data outside their permission.

## Likely causes
1. **String concatenation/f-strings/`.format()` building SQL directly**
   from request parameters, path segments, headers, or any other
   attacker-influenced value.
2. **An ORM's "raw query" escape hatch used with unparameterized input**
   (e.g. `.raw()`, `.execute(f"...")`) when the ORM's normal query builder
   would have parameterized it automatically -- often introduced for a
   "complex query the ORM can't express," bypassing its safety net along
   with its convenience.
3. **Dynamic identifiers (table/column names) built from user input**,
   which parameterization doesn't cover (bind parameters are for values,
   not identifiers) -- a common gap even in otherwise-parameterized code.
4. **Second-order injection**: a value stored safely (already
   parameterized on write) is later read back and concatenated into a
   *different* query unsafely, so the vulnerability isn't visible at the
   original input point at all.

## Diagnose
- Grep for string formatting/concatenation feeding into any SQL
  execution call (`execute`, `raw`, `query`) across the codebase, not
  just the specific endpoint that was reported.
- For ORM raw-query escape hatches specifically, check every use for
  whether the interpolated value is attacker-influenced.
- For dynamic identifiers, check whether table/column names are ever
  built from user input rather than a fixed allowlist.
- For second-order cases, trace where a stored value is later read and
  used in another query, not just its original write path.

## Fix
- Use parameterized queries / bind parameters for every value that
  originates from outside the application (`execute(query, (user_id,))`,
  not string interpolation) -- this is the primary, complete fix for
  standard injection, not a mitigation.
- For dynamic identifiers, validate against a strict allowlist of known-
  safe table/column names (never interpolate the raw input directly),
  since parameterization doesn't apply to identifiers.
- For ORM raw-query escape hatches, prefer the ORM's parameterized raw-
  query form (most ORMs support parameters even in raw mode) over plain
  string formatting; if the ORM truly can't express it safely, treat the
  whole query as security-sensitive code requiring extra review.
- For second-order injection, apply the same parameterization fix at
  every point data is used in a query, not just the original input point
  -- a value being "already validated on write" doesn't make it safe to
  concatenate on read.

## Pitfalls
- "Sanitizing" input by blocklisting specific characters (stripping
  quotes, escaping `%`) is fragile and routinely bypassed by encoding
  tricks or characters the blocklist didn't anticipate -- parameterization
  is the fix, escaping/blocklisting is not a substitute for it.
- Fixing the reported endpoint without grepping for the same pattern
  elsewhere leaves the same vulnerability class present in sibling code
  -- treat one injection report as a signal to audit the whole codebase
  for the same anti-pattern, not just patch the one instance.

## Verify
Attempt the specific injection payload that was reported (or a standard
one like `' OR '1'='1`) against the fixed endpoint and confirm it's
treated as literal data (e.g. searched for verbatim, or rejected by type
validation) rather than altering the query's structure or returning
unauthorized data.
