---
name: session-data-inconsistency-multi-server-file-driver
description: Users get logged out or lose cart/form state intermittently in production because sessions are stored on local disk behind a multi-server load balancer.
triggers: ["users randomly logged out laravel", "session data lost intermittently", "laravel session file driver multiple servers", "session inconsistent behind load balancer"]
permissions: ["READ"]
---

## Symptom
Users report being randomly logged out, losing items from a cart, or
seeing stale/incorrect flash messages -- but only sometimes, and it can't
be reproduced reliably in staging (which runs a single server). It
correlates with load-balanced production traffic and often gets worse
right after scaling out to more app servers or during a deploy that
restarts instances.

## Likely causes
1. **`SESSION_DRIVER=file` (the Laravel default) with more than one app
   server behind a load balancer**, and no sticky sessions configured --
   each server writes session files to its own local disk
   (`storage/framework/sessions`), so a user whose requests get routed to
   a different server than the one that created their session finds no
   matching session file and appears logged out or with an empty session.
2. **Sticky sessions (session affinity) are configured at the load
   balancer, masking the underlying problem** until a server is removed
   from rotation (deploy, autoscaling scale-in, health-check failure) --
   at that point every user pinned to that server loses their session
   simultaneously, which looks like a sudden mass-logout incident rather
   than a gradual, explainable one.
3. **`storage/framework/sessions` isn't a genuinely shared/networked
   filesystem even though it "looks" shared** -- e.g. servers were
   provisioned from the same image/AMI so the directory structure looks
   identical, but each server has its own independent local disk, not an
   actual shared mount (NFS/EFS), so there's no real sharing happening
   despite the directories having the same path.
4. **Session garbage collection or a differing `SESSION_LIFETIME` across
   servers (e.g. one server wasn't redeployed with a config change)**
   causes sessions to expire at different times depending on which server
   happens to run garbage collection, compounding the inconsistency on
   top of the fundamental file-driver-not-shared problem.

## Diagnose
- Check `SESSION_DRIVER` in the production `.env`/config -- `file` is the
  default if never explicitly set, so a team that never deliberately
  chose a session driver is very likely on this by accident.
- Confirm the deployment topology: how many app server instances are
  running, whether there's a load balancer in front of them, and whether
  it currently uses sticky sessions (check the load balancer's
  configuration, e.g. an AWS ALB target group's stickiness setting or an
  nginx `ip_hash` directive upstream).
- On two different app servers, list `storage/framework/sessions` during
  active traffic and confirm whether the *same* session ID's file exists
  on only one server (proving they're independent local disks) versus
  visible identically on both (which would indicate an actual shared
  mount already in place).
- Correlate user-reported logout timestamps with deploy/restart/
  autoscaling events in infrastructure logs -- a strong correlation
  points at server-affinity loss rather than a session-expiry
  configuration issue.

## Fix
- Move sessions to a driver that's inherently shared across all app
  servers: `redis` or `database` are the standard choices for a
  multi-server Laravel deployment -- both centralize session storage so
  any server can read any user's session regardless of which server
  handled the previous request.
- If moving off `file` isn't immediately possible, sticky sessions are a
  stopgap, not a fix -- they hide the problem during normal operation but
  still cause a mass-logout the moment a server leaves rotation (deploy,
  scale-in, crash), so treat centralized session storage as the actual
  target, with stickiness only as a temporary bridge.
- After switching drivers, confirm `SESSION_CONNECTION` (for redis) or
  the sessions table/migration (for database) is configured identically
  across every server's config -- a driver switch that's only deployed to
  some servers reintroduces the exact same inconsistency at a different
  layer.
- Ensure `SESSION_LIFETIME` and any custom garbage-collection
  configuration is identical across all servers (it should be, since
  config comes from the same deployed `.env`/config files, but verify
  after any partial/rolling deploy) so expiry behavior doesn't vary by
  which server happens to serve a given request.

## Pitfalls
- Switching to `redis` for sessions but pointing it at a single
  non-replicated Redis instance with no persistence/failover reintroduces
  a single point of failure -- a Redis restart now logs out every user
  simultaneously instead of a subset, which can be a worse incident than
  the one being fixed if Redis isn't set up with appropriate durability
  for this use case.
- Relying on sticky sessions indefinitely without ever fixing the
  underlying driver means the system silently accumulates risk that
  surfaces at the worst time (a large autoscaling event, a rolling
  deploy touching many servers at once) rather than being fixed on a
  predictable schedule.
- Forgetting to migrate/invalidate old file-based sessions during the
  cutover means users active at the moment of the driver switch get
  logged out once (expected, one-time), which is fine, but should be
  communicated/scheduled rather than mistaken for the bug persisting
  after the fix.

## Verify
After switching drivers, log in on one app server (or force routing to
a specific instance if testing directly against instances behind the
load balancer), then make a subsequent request that a load balancer
would route to a *different* server, and confirm the session persists
(the user stays logged in, cart/flash data survives) without relying on
sticky-session affinity. Separately, simulate a server being removed from
rotation (or a rolling deploy) and confirm active users aren't logged out
as a result.
