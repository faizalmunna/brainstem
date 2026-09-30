---
name: lambda-vpc-cold-start-timeout
description: A Lambda function attached to a VPC times out intermittently on cold starts while warm invocations complete quickly and reliably.
triggers: ["lambda timing out intermittently", "lambda cold start vpc timeout", "lambda eni attachment slow", "vpc lambda slow first invocation", "lambda task timed out no obvious cause"]
permissions: ["READ"]
---

## Symptom
A Lambda function configured to run inside a VPC (to reach an RDS instance,
an internal ALB, or another private resource) times out on some
invocations -- usually the first invocation after a period of inactivity,
after a deploy, or during a burst of concurrency -- while subsequent
invocations on an already-warm execution environment complete well within
the configured timeout. CloudWatch shows the timeout duration elapsed with
no application-level error, just a `Task timed out after N.00 seconds`.

## Likely causes
1. **ENI attachment/cold-start latency for VPC-enabled functions** -- when
   a new execution environment is created for a VPC-attached function, AWS
   must attach (or reuse from a warm pool) an elastic network interface in
   your subnet before your code can reach anything on that VPC; under
   Hyperplane ENI pooling this is much faster than it used to be, but it is
   still not zero, and a burst of concurrency that outpaces the warm ENI
   pool creates a new round of attachment latency.
2. **The function's actual timeout is too tight for cold-start-plus-work**,
   so it was already only marginally sufficient on a warm start and cold
   start's added overhead (interpreter/runtime init, dependency import,
   ENI readiness) pushes it over.
3. **A downstream dependency (RDS, an internal service) is itself slow to
   accept new connections on a cold path** -- e.g., establishing a fresh
   TCP/TLS handshake and doing auth against a database for the first time
   in that execution environment, which is conflated with "VPC cold start"
   but is actually connection-establishment cost, not ENI cost.
4. **DNS resolution inside the VPC is slow or failing intermittently**
   because the VPC's DNS settings (`enableDnsSupport`/`enableDnsHostnames`)
   or a custom DHCP option set/resolver isn't configured the way the
   function's code assumes, adding retries/timeouts before the real work
   even starts.
5. **Provisioned Concurrency is not enabled and traffic is spiky**, so a
   meaningful fraction of invocations are cold by construction, and the
   timeout budget was sized only around warm-path latency.

## Diagnose
- In CloudWatch Logs for the function, compare `Init Duration` (present
  only on cold starts, in the `REPORT` line) against total `Duration` for
  timed-out vs. successful invocations -- a large `Init Duration` on the
  failures points at cold start, not application logic.
- Check whether timeouts cluster around deploys, scale-up events, or after
  idle periods (via invocation count graphs) -- clustering there confirms
  cold-start correlation rather than a steady-state bug.
- If the AWS account/region predates the 2019 Hyperplane ENI change or the
  function was recently moved into a new VPC/subnet, check subnet IP
  address exhaustion (`DescribeSubnets` available IP count) -- if the
  subnet is nearly full, new ENI creation can fail or be delayed, compounding
  cold-start latency.
- Add explicit timing instrumentation (timestamp at handler entry vs. after
  DB connect) to separate "time to start running my code" from "time my
  code took to connect to the database," since both get lumped into the
  same visible timeout otherwise.
- Check X-Ray traces (if enabled) for the initialization segment duration
  specifically.

## Fix
Treat this as a budget problem, not a single bug: raise the function
timeout enough to absorb realistic cold-start variance with margin, but
also reduce how often cold starts happen and how expensive each one is.
Enable Provisioned Concurrency (or Lambda SnapStart, where the runtime
supports it) for latency-sensitive functions so a pool of pre-initialized,
already-VPC-attached environments absorbs traffic without paying ENI/init
cost per request. Move any one-time-expensive setup (DB connection,
SDK client construction, dependency loading) to the top level of the
function file, outside the handler, so it runs once per execution
environment instead of once per invocation. Ensure subnets used by the
function have ample free IP addresses and span multiple AZs so ENI
creation isn't constrained. If the function doesn't actually need to reach
a VPC-private resource (e.g., it only calls public AWS APIs), remove VPC
configuration entirely -- that eliminates ENI-related cold-start cost as a
factor altogether.

## Pitfalls
Blanket-increasing the timeout to "make the errors go away" without
checking `Init Duration` can mask a real regression in warm-path logic
(e.g., a slow query) by giving it enough runway that it stops erroring
while still being much slower than it should be. Enabling Provisioned
Concurrency without accounting for its cost implication (you pay for
allocated capacity whether invoked or not) on a low-traffic function is
also a common overcorrection -- size it to actual traffic patterns, not to
"never cold start again."

## Verify
After the fix, filter CloudWatch Logs Insights for `Init Duration` across
a representative traffic window and confirm cold starts either
(a) no longer occur for provisioned-concurrency-covered invocations, or
(b) complete comfortably inside the timeout with margin. Re-run the same
burst-of-concurrency scenario that originally triggered timeouts (a load
test hitting the function from zero warm environments) and confirm no
`Task timed out` entries appear.
