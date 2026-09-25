---
name: mongodb-schema-validation-bypassed-by-legacy-writes
description: Diagnose inconsistent or malformed documents appearing in a MongoDB collection despite a JSON Schema validator being configured on it.
triggers: ["documents dont match schema validator", "mongodb validation not catching bad documents", "inconsistent document shape in collection", "schema validator not enforced", "malformed documents despite validation rules"]
permissions: ["READ"]
---

## Symptom
A MongoDB collection has a `$jsonSchema` validator configured, and yet
documents exist in the collection that violate it -- missing required
fields, wrong types, or values outside an expected enum -- causing
downstream application code (which assumed the validator guaranteed
shape) to throw unexpected errors or silently misbehave when it
encounters one of these documents.

## Likely causes
1. **Validator applied with `validationLevel: "moderate"`**, which only
   validates new inserts and updates to *already-valid* documents,
   deliberately skipping validation on updates to documents that were
   already invalid before the validator was added -- so pre-existing
   bad documents can persist and even continue to be updated without
   ever being forced into compliance.
2. **Validator added after the collection already contained invalid
   documents**, with no backfill/cleanup pass run against the existing
   data -- schema validation in MongoDB is enforced on writes, not
   retroactively on existing data, so adding a validator doesn't touch
   documents already in the collection.
3. **`validationAction: "warn"` instead of `"error"`** -- this logs a
   validation failure but still allows the write to proceed, which is
   sometimes chosen deliberately during a rollout period but then never
   revisited and switched to enforce mode, so the validator effectively
   never blocks anything.
4. **A write path bypasses the driver/application layer entirely** (a
   direct `mongosh` script, an admin tool, a data migration job, or a
   different service with its own connection) and either targets the
   collection with `bypassDocumentValidation: true` or simply predates
   awareness that validation exists, producing documents the "normal"
   application write path would have rejected.
5. **The validator schema itself doesn't cover every field/invariant
   the application actually assumes** -- documents can be fully valid
   per the configured `$jsonSchema` and still violate an assumption the
   application code makes that was never encoded into the schema.

## Diagnose
- Check the collection's current validator configuration via
  `db.getCollectionInfos({name: "collection"})` and inspect
  `options.validationLevel` and `options.validationAction` -- confirm
  whether it's `"strict"`/`"error"` (fully enforced) or a weaker
  combination.
- Query directly for documents violating the intended shape (e.g.
  `db.collection.find({ requiredField: { $exists: false } })` or a
  `$jsonSchema`-based `$match` in an aggregation using `$expr`) to find
  and count how many existing documents are actually non-conforming,
  independent of what the validator is configured to do going forward.
- Check application/audit logs (or MongoDB logs, if validation warnings
  are logged) for `bypassDocumentValidation` usage, and audit which
  services/scripts have write access to the collection outside the
  primary application code path.
- Check when the validator was added (via change history/migration
  logs) relative to when the offending documents were created
  (`_id` embeds a creation timestamp that can help date documents
  without an explicit timestamp field) to confirm whether they predate
  the validator.

## Fix
- Set `validationLevel: "strict"` and `validationAction: "error"` once
  ready to fully enforce, and treat any transition period using `"warn"`
  or `"moderate"` as explicitly temporary -- schedule and execute the
  switch to full enforcement rather than leaving it indefinitely.
- Run a backfill pass to bring existing non-conforming documents into
  compliance (or explicitly quarantine/flag them for manual review if
  they can't be automatically fixed) before or immediately after
  tightening validation, so `"strict"` mode doesn't start silently
  blocking legitimate updates to those pre-existing bad documents.
- Audit every write path with access to the collection (not just the
  primary application) for `bypassDocumentValidation` usage or
  out-of-band writes, and require an explicit, reviewed justification
  for any legitimate use of the bypass (e.g. a controlled migration
  script), rather than allowing it as an unnoticed default.
- Treat the `$jsonSchema` validator as a baseline safety net, not a
  substitute for application-level validation -- encode invariants the
  application actually relies on explicitly in the schema (required
  fields, types, enums) rather than assuming implicit conventions are
  covered.

## Pitfalls
- Switching straight to `"strict"`/`"error"` without first finding and
  fixing existing bad documents causes legitimate updates to those
  documents to start failing in production, turning a data-quality
  issue into an availability issue for whatever depends on updating
  those records.
- Adding a validator and assuming it retroactively cleans the
  collection -- it does not; validation is a write-time gate, not a
  standing data-quality guarantee for data already present before it
  was added.
- Over-restricting the schema (marking fields required or typed too
  strictly relative to genuine legitimate variation) can block valid
  writes just as much as it blocks bad ones -- validate against real
  application requirements, not an idealized schema that doesn't
  account for legitimate optional/evolving fields.

## Verify
Query the collection for documents violating the intended shape and
confirm the count is zero (or fully accounted for in an explicit
quarantine), then attempt a write that violates the schema directly
(e.g. via `mongosh`) and confirm it's rejected with a validation error
under the collection's current `validationLevel`/`validationAction`
settings.
