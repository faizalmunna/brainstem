---
name: shared-airflow-connection-change-breaks-other-dags
description: A shared Airflow connection or variable gets modified for one team's need and silently breaks unrelated DAGs that depended on its previous configuration.
triggers: ["airflow connection change broke other dags", "shared variable update broke unrelated pipeline", "airflow connection id used by multiple teams", "changed connection now other dag fails", "airflow variable overwritten unexpected"]
permissions: ["READ"]
---

## Symptom
Someone updates an Airflow connection (a database host, a set of
credentials, extra JSON config) or an Airflow Variable to support a
change their team needs, their own DAG works fine afterward -- and then,
hours or days later, a completely different, unrelated DAG owned by
another team starts failing, and it's not obvious why, because nobody
told that team anything changed and their DAG's code didn't change at
all.

## Likely causes
1. **A single `conn_id` (e.g., `snowflake_default`, `postgres_prod`) is
   reused across many DAGs owned by different teams** as a matter of
   convenience/convention, so it functions as shared global mutable
   state -- any edit to its host, schema, role, or extra parameters
   affects every DAG referencing that same `conn_id`, whether or not the
   editor knew about the other consumers.
2. **An Airflow Variable holding a config value (a table name, a
   threshold, a feature flag) is named generically** (`target_schema`,
   `batch_size`) and reused by multiple DAGs that each assumed they were
   the only consumer, so a change intended for one DAG's context silently
   changes behavior for all of them.
3. **No ownership or documentation exists for shared connections/
   variables** -- there's no record of which DAGs reference a given
   `conn_id`/`Variable.get(...)` call, so anyone editing one has no way
   to know, short of grepping every DAG file in the repository, who else
   depends on it.
4. **Connections/variables are edited directly in the Airflow UI or via
   the CLI against the live metadata database**, with no review process,
   version history, or diff -- unlike a code change to a DAG file, this
   kind of change often isn't reviewed by anyone besides the person
   making it.

## Diagnose
- Grep the entire DAGs repository for the exact `conn_id` string or
  `Variable.get("...")` key involved, across all DAG files, not just the
  one that prompted the change -- this directly enumerates every actual
  consumer.
- Check the connection/variable's edit history if available (some
  Airflow setups version this via infrastructure-as-code / a
  `variables.json`/Terraform-managed connections file; others only have
  the live UI with no history) -- if there's no history, the "who changed
  what, when" question has to be reconstructed from DAG failure
  timestamps correlating with when someone recalls making the change.
- Compare the failing DAG's expectations (what host, schema, or config
  value its code assumes) against the connection/variable's current
  actual value, to confirm the mismatch directly rather than assuming.
- Ask whether the connection/variable was managed as code (checked into
  version control, applied via CI) or edited ad hoc in the running
  Airflow instance -- this determines whether the change is even visible
  in a diff anywhere.

## Fix
Stop treating widely-shared, generically-named connections/variables as
free to edit unilaterally. Where multiple teams' DAGs need
similar-but-not-identical configuration, give each consumer its own
scoped `conn_id`/Variable (namespaced by team or DAG, e.g.,
`snowflake_team_a` vs `snowflake_team_b`) rather than one shared default
that everyone happens to point at, even if the underlying values start
out identical -- this makes a future change to one team's needs
structurally unable to affect another's. Where a connection genuinely
must be shared (a single production warehouse connection used
read-only by many DAGs, for example), manage it as code (Airflow
supports defining connections/variables via environment variables or a
secrets backend driven by version-controlled config) so changes go
through the same review process as any other pipeline change, are
visible in a diff, and can be attributed and reverted. Document, even
minimally, which DAGs consume which shared connections/variables so a
future editor can check blast radius before changing one.

## Pitfalls
- Namespacing connections per-team but then copy-pasting credentials/
  config between them, so they drift independently over time and nobody
  notices when the underlying database they point at actually does need
  a coordinated update (e.g., a credential rotation) across all of them.
- Moving connections into code/CI-managed config but leaving the
  production Airflow instance's existing UI-managed connections in place
  as an untouched fallback, creating two sources of truth that can
  disagree about a connection's actual current value.
- Adding per-team scoping only for connections, while variables (often
  just as impactful, e.g., a shared `batch_size` or `enable_feature`
  flag) remain global and generically named, leaving half the original
  problem in place.

## Verify
After scoping the connection/variable, grep the DAGs repository again
for the old shared `conn_id`/Variable key and confirm zero remaining
references outside the intended owner, then trigger the previously-
broken unrelated DAG and confirm it runs successfully using its own
scoped configuration, unaffected by any subsequent change to the other
team's connection.
