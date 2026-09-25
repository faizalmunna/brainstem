---
name: rag-metadata-filter-permission-scope-leak-or-overblock
description: A metadata filter meant to scope retrieval to a document category or permission level either leaks content across access boundaries or wrongly blocks valid results.
triggers: ["RAG leaked a document a user shouldn't see", "permission scoped search returns nothing", "metadata filter not restricting results", "user sees content from another tenant", "access control bug in retrieval"]
permissions: ["READ"]
---

## Symptom
Two distinct but related failure directions, both traced to the same filtering mechanism: (a) **under-restriction/leak** -- a user retrieves or is answered with content from a document category, tenant, or permission tier they should not have access to, discovered either by a security review or, worse, by an affected user noticing; (b) **over-restriction** -- a user with legitimate access gets an empty or thin result set for a query that should clearly match documents they're entitled to see, because the filter excludes valid results along with the intended ones.

## Likely causes
1. **The permission/category filter is applied only at the prompt-construction stage (after retrieval), not at the retrieval query itself**, so the vector search runs unscoped, retrieves whatever is most similar regardless of access level, and filtering happens too late -- by the time results are filtered, sensitive content has already been fetched and (in a leak scenario) filtering is skipped, forgotten, or bypassed in some code path.
2. **Metadata used for filtering is missing, incorrect, or inconsistently populated on a subset of chunks** -- e.g., a document was ingested before a "tenant_id" or "access_level" field was introduced into the schema, or a bulk-import path doesn't set the field at all, leaving those chunks either filterable-as-public by default (leak) or invisible to every filter (over-block), depending on how the query handles nulls.
3. **Filter logic uses OR where AND was intended (or vice versa) across multiple scoping dimensions** -- e.g., a user with access to "public" documents AND their own "team" documents gets a filter that's supposed to be `category=public OR team_id=X` but is implemented as `category=public AND team_id=X`, which over-restricts to the intersection instead of the union.
4. **Filter values passed at query time don't match the exact format/casing/type stored in metadata** (a user's team ID passed as a string vs. stored as an integer, or a category value with inconsistent casing), causing the filter to silently match nothing even though the data and permission logic are otherwise correct.

## Diagnose
- Trace a specific leak or over-block report to the exact filter clause sent to the vector store for that query (log the full filter expression, not just "a filter was applied") and compare it against what the user's actual permissions should produce.
- Query the vector store's metadata directly for a sample of chunks from the document(s) involved and check whether the access-control field is present, non-null, and correctly valued -- distinguishes a data-quality problem from a logic problem.
- For a suspected leak, reproduce with a test account scoped to a known restricted permission level and directly inspect the raw retrieval results (before any generation step) to confirm whether the leak is in retrieval itself or introduced later when constructing the prompt.
- Audit whether filtering is enforced at the database/vector-store query level (a `WHERE`/filter clause sent as part of the similarity search) versus only as a post-retrieval application-code filter -- the latter is inherently more fragile since every call site must remember to apply it.

## Fix
Enforce access filtering as a mandatory, non-optional parameter of the retrieval query itself (pushed down into the vector store's native filter/pre-filter capability), not as a post-hoc filter applied by application code after results come back -- this removes an entire class of "someone forgot to filter" bugs by making unscoped retrieval structurally impossible rather than merely discouraged. Backfill and validate access-control metadata on all existing chunks as part of any schema change that introduces a new scoping field, with a default that fails closed (treat missing/null access metadata as maximally restricted, never as public) rather than failing open. Write the boolean scoping logic (union vs. intersection across permission dimensions) explicitly and unit-test it against representative multi-dimension permission scenarios, rather than trusting it reads correctly by inspection.

## Pitfalls
- "Fixing" an over-restriction bug by loosening the filter without root-causing whether the loosening reintroduces the leak direction -- permission filter bugs are two-sided, and a fix validated only against the over-block complaint can silently reopen a leak.
- Relying solely on end-to-end testing with a couple of manually-checked accounts rather than systematic tests across every permission tier and boundary condition (a user with access to zero categories, a user with access to all categories, a newly-created document with not-yet-set metadata) -- access-control bugs concentrate at edge cases, not the common-case path that's usually the only one tested.

## Verify
Reproduce both the original leak/over-block report with a real or test account at the exact affected permission level and confirm correct behavior; run an automated permission-boundary test suite that checks retrieval results for accounts at each distinct permission tier against an expected allow/deny set of documents, and confirm it passes and is wired into CI so a future filter-logic change can't silently regress it.
