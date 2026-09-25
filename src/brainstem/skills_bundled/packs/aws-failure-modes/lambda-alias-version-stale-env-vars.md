---
name: lambda-alias-version-stale-env-vars
description: A Lambda function keeps running old code or old environment variable values after a deploy because an alias or event source is pinned to a specific prior version.
triggers: ["lambda not picking up new environment variables", "lambda alias pointing to old version", "lambda deploy not taking effect", "lambda still running old code after update", "lambda version pinning stale config"]
permissions: ["READ"]
---

## Symptom
After deploying a Lambda update (new code, or just updated environment
variables), invocations continue to behave as if the old configuration is
still active -- old environment variable values are read, or old code
paths execute -- even though the console/CLI shows the function's `$LATEST`
has the new configuration, and redeploying again doesn't change the
observed behavior.

## Likely causes
1. **An alias (e.g., `prod`, `live`) is pinned to a specific numbered
   version, and traffic is invoked via the alias ARN, not `$LATEST`** --
   publishing a new version and updating `$LATEST` does nothing to an
   alias until the alias itself is explicitly repointed at the new
   version; this is the single most common cause and is easy to miss
   because the console's default view often shows `$LATEST`, giving a
   false impression that "the function" has been updated.
2. **Event source mappings (API Gateway integration, EventBridge rule
   target, SQS trigger) reference a specific qualified ARN
   (`function:version` or `function:alias`)** that wasn't updated as part
   of the deploy pipeline, so new events keep invoking the old pinned
   target regardless of what `$LATEST` contains.
3. **Environment variables were changed on `$LATEST` but a published
   version snapshots configuration at publish time** -- each published
   version is immutable, including its environment variables, so
   updating env vars after a version was published doesn't retroactively
   change that version; only a newly published version (or `$LATEST`
   itself) reflects the update.
4. **Weighted alias traffic shifting (canary/linear deployment)** is
   mid-rollout, so a meaningful fraction of invocations are still
   deliberately hitting the old version by design, and what looks like
   "the deploy didn't take" is actually a partially-complete traffic
   shift that hasn't finished per its configured interval.
5. **A deployment pipeline (CodeDeploy, CI/CD) failed partway through an
   alias update** (e.g., a post-deployment hook or health check failed),
   leaving the alias pointed at the previous version as a safety
   rollback, without clearly surfacing that the "deploy" didn't
   actually complete.

## Diagnose
- Check exactly which ARN is being invoked in the failing path: the raw
  function ARN (`$LATEST` implicitly), a `:version` suffix, or a
  `:alias` suffix -- `aws lambda get-alias` shows precisely which
  version number an alias currently points to.
- For API Gateway/EventBridge/SQS triggers, inspect the actual configured
  target ARN (`aws apigateway get-integration`, `aws events
  list-targets-by-rule`, `aws lambda list-event-source-mappings`) rather
  than assuming it tracks `$LATEST` automatically -- qualified ARNs are
  static until explicitly changed.
- Compare the environment variables on the specific version being invoked
  (`aws lambda get-function-configuration --qualifier <version>`) against
  `$LATEST`'s configuration -- a mismatch here directly confirms cause 3.
- If using CodeDeploy for Lambda traffic shifting, check the deployment's
  current status (`aws deploy get-deployment`) -- an `In Progress` or
  `Failed`/`Stopped` status explains partial or reverted traffic
  immediately.
- Check CloudTrail for `UpdateAlias` events to confirm whether the alias
  was actually repointed as part of the deploy, and when.

## Fix
Treat "deploy" as meaning "update the artifact that traffic actually
points at," which for an aliased function means publishing a new version
*and* updating the alias to point to it (`aws lambda update-alias
--function-name X --name prod --function-version N`), not just updating
`$LATEST`. Ensure the deploy pipeline's final step explicitly repoints
every alias and every qualified event-source-mapping ARN used in
production, and make that step's success a required condition for the
pipeline reporting the deploy as complete. For CodeDeploy-managed
traffic shifts, wait for (or explicitly monitor) the deployment to reach
`Succeeded` before considering the rollout complete, and alert on
`Failed`/`Stopped` deployments rather than assuming success. For
environment-variable-only changes, remember these still require a new
published version if any alias/event source targets a pinned version
rather than `$LATEST`.

## Pitfalls
Pointing all event sources directly at `$LATEST` to "avoid this problem
entirely" removes the safety benefit that pinned aliases and versioned
deploys exist for (atomic cutover, easy rollback, canary shifting), and
reintroduces risk of an in-progress deploy being invoked mid-update. The
better fix is understanding and correctly automating the alias-repoint
step, not bypassing versioning. Also, manually repointing an alias
during an in-progress CodeDeploy traffic shift can conflict with and
corrupt the deployment's own state tracking -- let an in-progress
deployment finish or explicitly stop it first.

## Verify
After redeploying with the alias-repoint step included, invoke the
function through the actual production-facing entry point (not a direct
`$LATEST` test invocation) and confirm the response/logs reflect the new
code and environment variables. Check `aws lambda get-alias` shows the
expected version number, and confirm the event source mapping's
configured ARN matches.
