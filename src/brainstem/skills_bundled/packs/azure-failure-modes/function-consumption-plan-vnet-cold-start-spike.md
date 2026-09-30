---
name: function-consumption-plan-vnet-cold-start-spike
description: An Azure Function on the Consumption plan has dramatically longer cold starts, sometimes 10-30+ seconds, only after VNet integration was added.
triggers: ["azure function cold start much slower after vnet integration", "function app timeout after adding vnet integration", "consumption plan function slow first request vnet", "regional vnet integration function app latency"]
permissions: ["READ"]
---

## Symptom
An Azure Function App on the Consumption (Y1) plan had acceptable cold-start
latency until regional VNet Integration was added (to reach a private
Storage account, SQL, or Key Vault endpoint). After that, cold starts on the
first request after idle -- or any request causing a scale-out to a new
worker -- jump from roughly 1-3 seconds to 10-30+ seconds or outright
`FunctionTimeoutException`, while the app behaves normally once warm.

## Likely causes
1. **Every new worker must join the VNet before serving traffic** --
   regional VNet Integration requires each newly allocated Consumption
   worker to attach to the delegated subnet before it can resolve DNS or
   reach any dependency, and that attachment is pure added latency on top
   of the normal cold-start init, unlike Premium/Dedicated plans where
   pre-warmed instances absorb most of it.
2. **The delegated subnet is too small or nearly exhausted** -- VNet
   Integration requires a dedicated subnet (`Microsoft.Web/serverFarms`
   delegation), and if it's sized `/28` or smaller, or already has other
   workloads consuming addresses, worker allocation queues or fails,
   compounding startup time under scale-out.
3. **DNS resolution for dependencies now traverses a private DNS zone or
   on-prem resolver through the VNet** instead of Azure's public DNS, and a
   slow or unreachable custom DNS server (configured via the VNet's DNS
   settings) adds seconds of resolution delay to every cold worker before
   it can even open its first outbound connection.
4. **`WEBSITE_VNET_ROUTE_ALL` is set to force all outbound traffic through
   the VNet**, including calls to public Azure services (Storage, Key
   Vault) that would otherwise go over the fast path, so every cold start
   now pays NSG/route-table evaluation and possibly a slower egress path
   (e.g., through a firewall or NAT gateway) for traffic that didn't need
   to be private at all.
5. **The Consumption plan's scale controller is spinning up new workers
   faster than the VNet integration subsystem can attach them**, common
   during sudden traffic bursts, so a growing fraction of concurrent
   requests land on workers still mid-attachment rather than an already-
   integrated warm one.

## Diagnose
- Compare `azure-functions-host` startup logs (Application Insights,
  `requests` and `traces` tables) for `Init Duration`-equivalent timing
  before and after VNet Integration was enabled on the same function --
  isolate whether the added time is in host init or in the network
  attach phase specifically.
- Check the delegated subnet's available address count in the Azure
  portal (Virtual Network > Subnets) -- if free addresses are low,
  worker allocation is a plausible bottleneck, not DNS or routing.
- Query Application Insights `dependencies` for the first outbound call
  per cold invocation (e.g., to Storage or Key Vault) and check its
  duration in isolation -- a multi-second first-call duration that drops
  to milliseconds on warm invocations points at DNS/routing, not function
  code.
- Check whether `WEBSITE_VNET_ROUTE_ALL` (or the newer `vnetRouteAllEnabled`
  site config) is set to `1`/`true`; if so, temporarily test with it
  disabled (routing only traffic that must be private through the VNet)
  to see if cold-start time drops.
- Use `az functionapp show` / Kudu's `/api/vfs` diagnostics or the
  Azure Functions "Diagnose and solve problems" blade's cold-start
  detector to confirm the pattern correlates with scale-out events, not
  a code-level regression.

## Fix
Treat VNet-attach latency as an unavoidable Consumption-plan cost and
either reduce how often it's paid or move to a plan tier where it's
amortized. If sub-second cold starts are a hard requirement, move the
Function App to the Premium plan (Elastic Premium), which supports
pre-warmed, always-ready instances that stay VNet-attached, eliminating
the per-cold-start attach cost entirely. If staying on Consumption,
right-size the delegated subnet (at least `/26`, more if scale-out bursts
are large) so address exhaustion never becomes a compounding factor, and
scope `WEBSITE_VNET_ROUTE_ALL`/`vnetRouteAllEnabled` narrowly -- route only
traffic to genuinely private endpoints through the VNet rather than all
egress, so public dependency calls keep using the fast path. If a custom
DNS server is configured on the VNet, verify it is highly available and
fast (sub-100ms) for the zones the function actually queries, or fall
back to Azure-provided DNS plus Private DNS Zones for the specific private
endpoints in use.

## Pitfalls
Switching to Premium plan to fix cold starts without also configuring
`preWarmedInstanceCount` (or leaving it at the default of 1) still leaves
scale-out bursts exposed to the same attach latency on the *next* new
instance beyond the warm pool -- size the pre-warmed count to the actual
burst pattern, not just "greater than zero." Also, don't set
`WEBSITE_VNET_ROUTE_ALL` to `0` reflexively to "fix" cold starts if the
function genuinely needs private connectivity for some calls -- that
silently breaks the private-only dependencies (e.g., a Storage account
with public network access disabled) instead of fixing latency, trading a
slow error for a hard failure.

## Verify
Re-run a scale-from-zero test (force the app to scale in by having zero
traffic for the idle-scale-in window, then send a burst of concurrent
requests) and compare `Init Duration`/cold-start timing in Application
Insights before and after the fix -- confirm cold starts for
Premium-with-prewarm land under 1-2 seconds, or that Consumption-plan
cold starts drop measurably once subnet sizing and route-all scoping are
corrected. Confirm via `dependencies` telemetry that only intended traffic
(private endpoints) shows VNet-routed latency characteristics and public
dependency calls remain fast.
