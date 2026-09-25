---
name: app-service-arr-affinity-stale-session-state
description: An App Service app scales to multiple instances and users intermittently see stale in-memory cache or session data because ARR affinity keeps rerouting them unpredictably.
triggers: ["app service users see stale session after scaling", "arr affinity sticky session issue", "app service load balancing inconsistent user state", "ARRAffinity cookie causing uneven load"]
permissions: ["READ"]
---

## Symptom
An App Service app scales out to multiple instances under load, and users
begin seeing inconsistent behavior tied to which instance served them --
stale cached data, being "logged out" randomly, or seeing a different
in-memory shopping cart/session state than a moment before. It's
intermittent and worsens as instance count grows, and restarting the app
or scaling back to one instance makes it disappear.

## Likely causes
1. **The app was designed as stateless (or assumed to be) but actually
   keeps session/cache state in local process memory**, so ARR affinity
   (App Service's default sticky-session mechanism, via the
   `ARRAffinity` cookie) was silently doing the job of keeping a user
   pinned to the instance holding their state -- and if affinity later
   breaks (cookie dropped, client doesn't send cookies, load balancer
   rebalances), that user's next request lands on a different instance
   with no memory of their state at all.
2. **ARR affinity is enabled but the client doesn't reliably return the
   cookie** -- API clients, mobile apps, or any client not behaving like a
   full browser (not persisting/returning cookies, or explicitly stripping
   them) never get pinned in the first place, so every request from that
   client type can land on a different instance regardless of affinity
   being "on."
3. **ARR affinity is enabled specifically because the app is stateful,
   but the intent was actually a stateless, horizontally scalable design**
   -- someone left the default `Client Affinity Enabled` setting untouched
   without realizing it papers over local session state, so the app
   "worked" at low scale by accident and only reveals the design flaw once
   traffic patterns cause enough cross-instance routing.
4. **A CDN, App Gateway, or Front Door sits in front of App Service and
   doesn't forward or preserve the `ARRAffinity` cookie**, so affinity that
   works fine when testing directly against the App Service URL silently
   stops working once the production traffic path through the additional
   layer is used, since that layer becomes the actual load-balancing point
   cookies need to survive.
5. **Instance restarts/redeploys during scale operations invalidate
   affinity for previously-pinned users** because the specific instance
   they were pinned to no longer exists, and the app has no fallback
   behavior for "affinity broke, state is gone" beyond appearing to reset.

## Diagnose
- Check whether `Client Affinity Enabled` is set to `On` in the App
  Service's Configuration > General settings (or `az webapp show --query
  clientAffinityEnabled`), and confirm whether the app's actual design
  assumption (stateless vs. stateful) matches that setting's presence.
- Inspect actual request/response headers from a real client session
  (browser devtools Network tab, or `curl -v` with cookie jar) to confirm
  whether the `ARRAffinity`/`ARRAffinitySameSite` cookie is being set and
  subsequently sent back on follow-up requests -- if it's missing on
  request 2, affinity isn't actually functioning for that client.
- If a CDN/App Gateway/Front Door is in front of the app, check its
  configuration for cookie-based session affinity/session persistence
  settings independently -- App Service's own ARR affinity cookie doesn't
  automatically propagate through an upstream load balancer unless that
  layer is also configured to honor or set its own affinity.
- Search application code for any static/singleton in-memory collections,
  `IMemoryCache` used without a distributed backing store, or in-process
  session state providers (e.g., ASP.NET's default `InProc` session mode)
  -- these are the concrete artifacts of the state-should-be-external
  problem.
- Reproduce with multiple instances forced (scale out manually to 2+) and
  script repeated requests from a client that doesn't preserve cookies
  (plain `curl` without `-b`/`-c`) to confirm state appears to reset
  randomly.

## Fix
Decide deliberately whether the app is stateless or stateful, and build
for the one it actually is rather than letting ARR affinity's default
"on" setting make that decision by omission. For an app intended to be
horizontally scalable, move session/cache state to an external, shared
store (Azure Cache for Redis for session/cache data, or a database-backed
session provider) so any instance can serve any request with identical
results, then disable Client Affinity entirely -- this also improves load
distribution, since affinity-pinned traffic can otherwise concentrate
unevenly on instances that happened to acquire popular users first. If the
app is genuinely stateful by design (rare, and usually a sign it should be
refactored), keep affinity on but ensure every layer in the actual traffic
path (CDN, Front Door, App Gateway) is configured to preserve or itself
implement session affinity end to end, not just at the App Service layer.

## Pitfalls
Disabling Client Affinity without first removing the in-memory state
dependency just changes an intermittent bug into a constant one -- users
would see wrong/missing state on nearly every request instead of only
after a rebalance. Conversely, "fixing" this by increasing affinity's
robustness (e.g., trying to force cookie stickiness through every proxy
layer) instead of externalizing state locks the app out of proper
autoscaling and makes instance failures user-visible, which defeats the
reason to run multiple instances at all.

## Verify
After externalizing state and disabling affinity, run the same
multi-instance repeated-request test (including a client that doesn't
preserve cookies) and confirm session/cache data is now identical
regardless of which instance actually serves each request -- check
`X-Powered-By`/instance ID response headers or Application Insights
cloud role instance data to confirm requests are indeed being served by
different instances during the test. Load-test with scale-out triggered
mid-test and confirm no user-visible state discontinuity occurs during the
scaling event.
