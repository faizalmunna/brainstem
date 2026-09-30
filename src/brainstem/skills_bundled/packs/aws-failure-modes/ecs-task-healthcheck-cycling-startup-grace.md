---
name: ecs-task-healthcheck-cycling-startup-grace
description: ECS tasks repeatedly fail health checks and get killed and replaced in a loop because the application's real startup time exceeds the configured health check grace period.
triggers: ["ecs task keeps restarting", "ecs service unstable deploying", "ecs health check grace period", "ecs task failing health check and cycling", "fargate task never becomes healthy"]
permissions: ["READ"]
---

## Symptom
An ECS service (EC2 or Fargate launch type) shows tasks starting,
briefly running, then being marked unhealthy and stopped, with the
service continuously launching replacements -- the deployment never
stabilizes, or it stabilizes only after many cycles, and CPU/memory on
the tasks that do get killed often look unremarkable right up until
they're terminated.

## Likely causes
1. **`healthCheckGracePeriodSeconds` (ALB/NLB target group health check
   grace period) is shorter than the application's actual cold-start
   time** -- if the app takes 60-90 seconds to warm up (loading models,
   running migrations, JIT warmup) but the grace period is the default or
   set to something shorter, the load balancer starts health-checking and
   failing the task before it's ever actually ready, and ECS interprets
   sustained health check failures as a reason to kill and replace it.
2. **The container-level health check (`HEALTHCHECK` in the Dockerfile or
   the ECS task definition's `healthCheck` block) has its own
   `startPeriod` set too low**, which is a *separate* grace period from
   the load balancer's -- fixing only the ALB-side grace period without
   also adjusting the container-level one leaves the other mechanism
   still killing the task prematurely.
3. **The health check endpoint itself does more work than a liveness
   check should** -- e.g., it checks downstream dependencies (database,
   cache) that are themselves slow to become available at startup, so the
   task's *own* process is fine but the health check fails because a
   dependency isn't ready yet, conflating "am I alive" with "are my
   dependencies ready."
4. **Insufficient task CPU/memory causes slow startup that varies
   invocation to invocation** -- a task sized too small spends longer
   than expected initializing under contention, so the grace period that
   was "usually enough" fails intermittently under load or when multiple
   tasks start simultaneously and compete for host resources (EC2 launch
   type) or during periods of a noisy neighbor.
5. **A dependency the container needs at startup isn't available yet in
   the deployment order** -- e.g., a task depends on a sidecar container
   in the same task definition that hasn't reached `HEALTHY` yet, and
   `dependsOn` conditions in the task definition aren't configured, so the
   main container starts before its sidecar is ready and fails its own
   check as a result.

## Diagnose
- Check ECS service events (`aws ecs describe-services`) for the specific
  reason tasks are stopped -- look for `Task failed ELB health checks` vs.
  `essential container in task exited` vs. an OOM/resource-related stop
  reason, since these point at different causes.
- Compare the application's actual measured startup time (time from
  container start to the app logging "ready"/serving traffic, found in
  CloudWatch Logs timestamps) against both the target group's
  `HealthCheckIntervalSeconds` x `UnhealthyThresholdCount` and the
  service's `healthCheckGracePeriodSeconds` -- if real startup time is
  close to or exceeds the grace period, that's the direct cause.
- If using a container-level `HEALTHCHECK`, check its `startPeriod`,
  `interval`, `timeout`, and `retries` in the task definition separately
  from the ALB target group settings -- these are independent mechanisms
  that must both be sized correctly.
- Hit the health check endpoint manually (via `ecs exec` into a running
  task, or locally) and time how long it takes and what it actually
  checks -- if it queries a database or external service, that's a
  design issue (cause 3), not just a timing issue.
- Check task definition `dependsOn` container ordering conditions if
  multiple containers are defined, and check the sidecar/dependency
  container's own health status timeline against the main container's
  first health check attempt.

## Fix
Set `healthCheckGracePeriodSeconds` on the ECS service to comfortably
exceed measured real-world startup time (including cold-start variance
under load, not just the best-case local measurement), and set the
container-level `HEALTHCHECK startPeriod` to a matching or longer value
so both mechanisms agree on how long "still starting up" means. Separate
liveness from readiness: the health check endpoint should confirm the
process itself can serve requests, not transitively verify every
downstream dependency -- if dependency readiness matters, model it as a
separate readiness gate (e.g., the app returns 503 from the health
endpoint until its own internal readiness flag is set, without making
the check block on a live database round-trip on every poll). Use
`dependsOn` with `condition: HEALTHY` or `START` in the task definition
for containers that genuinely must wait on a sidecar, instead of relying
on race-condition timing. If startup time is inflated by genuine resource
contention, increase task CPU/memory allocation and re-measure.

## Pitfalls
Setting the grace period extremely long "to be safe" delays real
detection of a task that's actually stuck/broken, since ECS won't act on
health check failures at all during the grace window -- a task that will
never become healthy just sits there consuming capacity for the full
grace period before anything happens. Also, making the health check
endpoint trivially return 200 unconditionally to "stop the cycling"
removes the signal entirely and can let a genuinely broken task serve
traffic as if healthy, which is worse than the original symptom.

## Verify
Deploy with the corrected grace period and startPeriod, then watch `aws
ecs describe-services` events through a full deployment cycle and confirm
tasks reach `RUNNING` and pass health checks on the first or second
attempt without being cycled. Separately, deliberately deploy a
build that's slow to start (or reduce grace period back temporarily in a
non-prod environment) to confirm the health check does still catch a
genuinely-never-ready task, so the fix hasn't disabled detection
entirely.
