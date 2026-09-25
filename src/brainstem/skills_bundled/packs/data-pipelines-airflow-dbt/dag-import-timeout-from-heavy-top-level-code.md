---
name: dag-import-timeout-from-heavy-top-level-code
description: Airflow's scheduler slows down parsing all DAGs or times out because one DAG file executes expensive work at import/parse time instead of inside a task.
triggers: ["airflow dag parsing slow", "scheduler cpu high all dags affected", "dag file import timeout", "airflow webserver slow to load dag list", "one dag slowing down entire scheduler"]
permissions: ["READ"]
---

## Symptom
The Airflow scheduler's overall performance degrades across the entire
deployment -- DAG parsing lag increases, the UI's DAG list is slow to
load, or the scheduler logs show DAG file processing taking many seconds
per file -- and it traces back to one or a few DAG files, not a
cluster-wide resource problem. Sometimes a specific DAG fails to even
appear in the UI, or appears with an import error after a timeout.

## Likely causes
1. **A DAG file makes a network call, database query, or API request at
   the top level of the module** (outside any operator/task, executed
   directly when the file is imported) -- for example, calling an API to
   dynamically fetch a list of tables and generate one task per table.
   The scheduler re-parses every DAG file on a repeating interval to
   detect changes, so this "setup" call re-executes on every single parse
   cycle, not once at deploy time.
2. **Heavy imports or computation at module level** (loading a large
   config file, importing a heavyweight library only actually needed
   inside one task, computing an expensive default argument) run once
   per parse cycle for that file, and multiplied across the scheduler's
   parsing loop and however many DAG files exist, this adds up to
   significant sustained CPU/latency load shared by every other DAG
   waiting to be parsed.
3. **Dynamic DAG generation from an external source (a database query, a
   config API) with no caching**, where the generation logic itself is
   slow or the external source is itself under load, compounding the
   parse-time cost with the external system's own latency and making the
   DAG file's parse time variable and occasionally very slow.
4. **A very large number of tasks generated dynamically in a loop at
   parse time** (thousands of tasks from a large list) increases parse
   time and scheduler/webserver memory/CPU load independent of any
   external call, simply from the size of the resulting DAG object graph.

## Diagnose
- Check the Airflow scheduler's DAG file processing metrics/logs
  (`DagFileProcessorManager` stats, or `airflow dags list-import-errors`
  and per-file parse duration if exposed) to identify which specific
  file(s) have outlier parse times compared to the rest of the
  deployment.
- Read the flagged DAG file for any code executed outside of an operator
  definition or a function only called inside a task's `execute`/
  `python_callable` -- specifically look for `requests.get(...)`,
  database connections, or `Variable.get(...)`/`Connection.get(...)`
  calls sitting at module level rather than inside a task.
- Time the file's import directly and in isolation
  (`python -c "import time; t=time.time();
  import dags.the_dag_file; print(time.time()-t)"`) to get a concrete
  number, and compare it against Airflow's configured
  `dag_file_processor_timeout` and the scheduler's overall parsing
  loop interval.
- Check how many `Task`/operator instances the file generates and
  whether that count is proportional to an external, possibly-growing
  data source (a table list, a customer list) rather than a fixed,
  small number.

## Fix
Move any expensive work out of module-level code and into task execution
time, or into a build/deploy-time step that runs once rather than on
every scheduler parse cycle. For dynamic DAG generation driven by an
external source, cache the result (write it to a local file checked into
the DAG repo, or a fast local cache with a TTL) so the DAG file reads a
cheap, fast local resource at parse time instead of re-querying a slow
external system on every parse; regenerate that cache on a separate,
explicit schedule (a CI job, a periodic script) rather than inline in the
DAG file's import path. Where a large, heavy library is only needed
inside one task's logic, import it inside the task function rather than
at the top of the file, so its import cost is paid once per task
execution rather than once per scheduler parse cycle for every DAG in the
deployment. If the true task count needs to scale with an external list,
consider whether dynamic task mapping (declared with a bounded, fast-to-
compute set of mapped inputs) is a better fit than generating a very
large static task list at parse time.

## Pitfalls
- Moving the expensive call into a task but leaving a lightweight-looking
  wrapper still doing meaningful work at module level (e.g., calling
  `Variable.get()` at the top of the file "just to configure defaults")
  -- even a single database round-trip per file per parse cycle adds up
  significantly at the scale of hundreds of DAG files parsed repeatedly.
- Caching an external source's data for DAG generation but never
  invalidating or refreshing it, so the DAG's task structure silently
  goes stale relative to the real source (new tables never get a
  corresponding task) without any error to signal the drift.
- Fixing one slow DAG file without checking whether the same anti-pattern
  (a top-level API call, a heavy import) was copy-pasted into other DAGs
  in the same repository from a shared template.

## Verify
Re-time the fixed DAG file's import in isolation and confirm it drops to
a small fraction of a second (well under the scheduler's per-file
processing budget), then check the scheduler's DAG file processing
metrics over a subsequent period and confirm both that file's parse time
and the overall scheduler parsing loop latency across all DAGs have
returned to baseline.
