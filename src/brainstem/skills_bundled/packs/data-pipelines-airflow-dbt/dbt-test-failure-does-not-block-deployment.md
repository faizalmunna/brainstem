---
name: dbt-test-failure-does-not-block-deployment
description: A dbt test such as not-null, unique, or relationships fails in CI but the pipeline still deploys or promotes the model to production anyway.
triggers: ["dbt test failed but deployed anyway", "dbt ci passes despite failing test", "dbt test not blocking pipeline", "failing dbt test ignored in production", "dbt build succeeded warnings ignored"]
permissions: ["READ"]
---

## Symptom
A dbt project has tests defined (`unique`, `not_null`, `relationships`,
or custom singular tests), and one of them fails during a CI run or
scheduled build -- yet the model still gets deployed/promoted, the
orchestrating DAG's downstream tasks still run, and the bad data reaches
production. The failure is visible somewhere in a log if you go looking,
but nothing about the deployment pipeline itself was actually gated by
it.

## Likely causes
1. **`dbt test` is run as a separate, disconnected CI step whose exit
   code isn't checked** -- a CI job runs `dbt test` after `dbt run` for
   visibility, but the pipeline's actual pass/fail gate is wired to the
   `dbt run` step's exit code (which succeeds even if the subsequent
   tests fail), so a test failure produces red text in a log nobody is
   required to read.
2. **Tests are configured with `severity: warn` when they should be
   `error`** -- dbt lets a test emit a warning instead of a failure,
   which is appropriate for genuinely advisory checks, but a `not_null`
   or `unique` test on a primary key silently downgraded to `warn`
   (often copy-pasted from an example, or loosened once to unblock a
   deploy and never tightened back) will never fail the build regardless
   of how bad the violation is.
3. **The orchestrating Airflow task wraps `dbt build`/`dbt test` and
   catches its non-zero exit code, logging it but returning success** --
   a `try/except` around a `subprocess.run(...)` call that doesn't
   re-raise or explicitly check the return code turns a real test failure
   into an Airflow task that reports green.
4. **Tests run against a different environment than what actually gets
   promoted** -- CI runs tests against a CI/staging schema built fresh,
   but the production deployment step doesn't depend on that CI test
   result at all (separate pipelines, no shared gate), so the two are
   only related by convention, not by an enforced dependency.

## Diagnose
- Inspect the CI pipeline configuration directly: does the job step
  running `dbt test` (or `dbt build`) have its exit code checked by the
  pipeline tool (e.g., not run with `continue-on-error: true` in GitHub
  Actions, or not piped through something that discards the exit status)?
- Grep dbt YAML config for `severity: warn` on tests protecting anything
  that should be a hard invariant (primary key uniqueness, required
  foreign keys, non-null critical columns) -- a `warn` severity there is
  very likely a misconfiguration, not an intentional choice.
- If dbt runs inside an Airflow `BashOperator`/`PythonOperator`, read the
  operator's code for how it invokes dbt and what it does with the
  return code -- look specifically for a caught exception or a checked
  `returncode` that gets logged but not re-raised.
- Trace whether the CI environment that runs `dbt test` is actually in
  the deployment path for production (does a failing CI run block a merge
  or a deploy trigger?), or whether it's an informational job running in
  parallel with an unrelated, ungated deploy mechanism.

## Fix
Make test failure structurally block promotion rather than relying on
someone reading logs. In CI, run `dbt build` (which runs models and their
associated tests together, halting downstream models when an upstream
test fails) rather than `dbt run` followed by a disconnected `dbt test`,
and ensure the CI job step is configured to fail the pipeline on a
non-zero exit code, with no `continue-on-error`/equivalent override. Set
`severity: error` (dbt's default) for any test protecting a real
invariant, reserving `severity: warn` deliberately and rarely for checks
that are genuinely informational (a soft data-freshness heads-up, for
example) rather than as a way to silence an inconvenient failure. In
Airflow, if dbt runs via a subprocess call, check and propagate its exit
code explicitly (raise an exception on non-zero) so the task itself goes
red and blocks `>>`-declared downstream tasks, rather than swallowing the
failure.

## Pitfalls
- Switching every `warn` test to `error` in one pass without checking
  whether any of them currently have real, unaddressed violations in
  production data -- this can turn on a hard gate that immediately blocks
  all future deploys until the underlying data issue is fixed, which is
  the right outcome but should be a planned cutover, not a surprise.
- Fixing the CI gate but leaving a separate, ungated scheduled
  production `dbt run` (without `test`) as the actual thing that updates
  production tables -- the CI gate then only protects merges, not the
  runtime pipeline that matters.
- Wrapping the now-enforced dbt failure in a blanket Airflow retry with
  no cap -- a deterministic data-quality failure will fail identically on
  every retry, so it should surface promptly rather than retry-loop for
  no benefit.

## Verify
Deliberately introduce a row that violates one of the "should be
blocking" tests (a duplicate primary key, a null in a not-null column) in
a test/staging dataset, run the actual CI pipeline (not just `dbt test`
locally) end to end, and confirm the pipeline reports overall failure and
that the corresponding Airflow DAG run (if one gates production) does not
proceed to the deployment/downstream task.
