---
name: pipeline-documentation-drifts-from-actual-logic
description: A dbt model's documented column descriptions or an Airflow DAG's description no longer match what the pipeline actually computes after logic changes.
triggers: ["dbt docs out of date", "dag description doesn't match what it does", "data lineage docs wrong", "column description doesn't match logic", "dbt docs generate stale metadata"]
permissions: ["READ"]
---

## Symptom
Someone consults dbt docs (`dbt docs generate`/`serve`) or an Airflow
DAG's description/task docstrings to understand what a pipeline does or
what a column means, makes a decision based on that description, and it
turns out to be wrong -- the model's logic changed at some point, or was
never fully described, and the documentation reflects an earlier or
aspirational version of the pipeline rather than what actually runs
today.

## Likely causes
1. **Documentation lives in a separate file/system from the logic it
   describes, with no enforced link between changing one and updating the
   other** -- a `schema.yml` column description or a DAG's `doc_md`
   is edited once at creation time and then never revisited when the SQL
   or task logic it describes changes.
2. **Code review doesn't treat documentation as part of the change** --
   a PR that changes a model's join logic or a task's filter condition
   gets reviewed and merged on the correctness of the SQL/Python alone,
   with nobody checking whether the accompanying description still
   describes the new behavior.
3. **Descriptions were written at a level of detail that goes stale fast**
   (restating specific implementation details like "filters to the last
   30 days" or "joins on customer_id") rather than describing stable
   intent, so any tuning change to the implementation invalidates the
   docs even when the model's purpose hasn't changed.
4. **No automated check compares documentation coverage/freshness against
   the actual DAG** -- dbt supports enforcing that models/columns have
   descriptions at all (a coverage check), but most projects don't run
   it, and even that check doesn't catch a description that's present but
   now wrong, only ones that are missing entirely.

## Diagnose
- Pick a handful of business-critical models/DAGs and read their current
  documentation side by side with their actual current SQL/task code --
  specifically check any description that names a concrete filter,
  threshold, join key, or schedule, since those are the details most
  likely to have quietly changed.
- Check version control history for the model/DAG file versus the
  history of its documentation (the `schema.yml` block or `doc_md`
  string) -- a long gap between the last logic change and the last
  documentation change is a direct, checkable signal of drift.
- Ask a recent consumer of the documentation (an analyst, another team)
  whether a decision they made based on it turned out to match reality --
  drift is often only discovered this way, so treat a reported mismatch
  as a symptom of a systemic gap, not just one isolated fix.
- Check whether dbt's documentation coverage is measured at all (`dbt
  docs generate` plus a coverage report, or a CI check enforcing
  descriptions on new models) -- if coverage is unmeasured, staleness is
  also unmeasured by definition.

## Fix
Bring documentation into the same review boundary as the code it
describes rather than treating it as a separate, optional artifact.
Practically: require that a PR changing a model's filter/join/grain or a
DAG's schedule/dependency also touches the corresponding `schema.yml`
description or `doc_md`/task docstring in the same PR, and call this out
explicitly in review -- "does the docstring still match?" as a standing
review question, the same way "are there tests?" is. Prefer documenting
stable *intent and grain* ("one row per customer per day, revenue
recognized net of refunds") over restating volatile implementation
details that change with every tuning pass, so descriptions have a
longer natural shelf life. For dbt specifically, use `{{ doc() }}` blocks
for shared, reusable descriptions (e.g., a `customer_id` definition used
across many models) so a single update propagates everywhere it's
referenced instead of needing to be repeated and separately kept in sync
in N places.

## Pitfalls
- Writing documentation so vague ("processes customer data") that it
  can never technically go "wrong," which avoids drift by being useless
  rather than by being accurate -- the goal is documentation specific
  enough to be worth reading, kept in sync, not documentation vague
  enough to never need updating.
- Treating a one-time documentation cleanup sprint as a permanent fix
  without changing the review process that let it drift in the first
  place -- the same gap will reopen gradually unless something (review
  culture, a checklist, a coverage gate) keeps enforcing it going forward.
- Auto-generating descriptions from column names or table comments as a
  substitute for someone verifying intent -- this produces plausible-
  looking documentation that can still be wrong about grain, filters, or
  business meaning, giving false confidence.

## Verify
For a model/DAG that was just brought back in sync, have someone who
didn't write the fix read only the documentation and describe back what
they believe the model computes and at what grain -- confirm their
description matches the actual SQL/task logic, not just that a
description field is non-empty.
