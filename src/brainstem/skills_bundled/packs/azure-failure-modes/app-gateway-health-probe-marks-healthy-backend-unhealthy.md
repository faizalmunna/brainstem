---
name: app-gateway-health-probe-marks-healthy-backend-unhealthy
description: Application Gateway or Front Door marks a functioning backend pool member unhealthy because the probe path or Host header doesn't match what the backend expects.
triggers: ["application gateway backend unhealthy but works fine directly", "front door health probe failing", "app gateway 502 backend marked down", "custom probe host header mismatch"]
permissions: ["READ"]
---

## Symptom
Azure Application Gateway or Front Door reports one or more backend pool
members as "Unhealthy," and traffic routed to the gateway returns 502
Bad Gateway, even though hitting the backend directly (its App Service
URL, VM IP, or internal load balancer) with the same request path returns
a normal 200 response.

## Likely causes
1. **The default health probe uses the backend pool's own hostname/IP as
   the `Host` header**, but the backend (especially an App Service, which
   routes by hostname) expects a specific `Host` header matching its
   custom domain or default `*.azurewebsites.net` name -- a probe sent
   with the wrong Host header can hit the backend's default document or a
   404 handler instead of the actual health endpoint, getting classified
   unhealthy despite the app being up.
2. **The probe path doesn't match an endpoint that actually exists or
   returns a 2xx/3xx**, either because it's still the default `/` path
   while the app has no meaningful response at root (e.g., an API-only
   backend that 404s on `/`), or a custom probe path was configured but
   the route requires authentication that the probe request doesn't/can't
   provide, so the probe legitimately gets a 401/403 that the backend
   considers correct behavior but the gateway considers unhealthy.
3. **Probe protocol/port mismatch** -- the probe is configured for HTTP
   while the backend setting expects HTTPS (or a non-standard port the
   backend actually listens on), so the probe connection itself fails
   before ever reaching application code, distinct from an application-
   level health check failure.
4. **The backend takes longer to respond to the probe than the configured
   probe timeout**, especially under load or during a cold start/warm-up
   period (e.g., an App Service instance still initializing after a scale
   event), so probes intermittently time out and the backend flaps between
   healthy and unhealthy even though it would eventually respond fine.
5. **A WAF rule or a separate NSG/firewall rule blocks the probe's
   specific source (Application Gateway's subnet, or Front Door's known
   IP ranges) while allowing normal user traffic through a different
   path**, so the probe is blocked at the network/WAF layer while real
   traffic through a CDN or different ingress point isn't subject to the
   same rule.

## Diagnose
- Check Application Gateway's **Backend health** blade (or Front Door's
  **Health Probe Log**) for the exact status code returned by the probe
  for each backend member -- a 401/403/404 versus a connection timeout are
  different problems requiring different fixes, and the blade shows this
  directly rather than requiring guesswork.
- Compare the configured probe's **Host name** setting (or "Pick host name
  from backend settings") against what the backend actually expects --
  for App Service backends specifically, test manually with `curl -H
  "Host: <expected-hostname>" https://<backend-ip-or-default-host>/<probe-path>`
  to reproduce exactly what the probe sees.
- Confirm the probe **path** resolves to a 200 (or an explicitly accepted
  status code range, if configured) when requested directly with the
  correct Host header and protocol -- don't assume `/` is a safe default
  for an API-only or SPA-only backend.
- Check probe **interval/timeout/unhealthy threshold** settings against
  the backend's actual startup/response time under realistic load,
  especially if unhealthy marks cluster around deploys or scale-out
  events rather than being constant.
- If a WAF policy is attached, check its logs for blocked requests
  originating from Application Gateway's or Front Door's own probe source,
  and check NSGs on the backend's subnet for rules that might exclude the
  gateway's subnet specifically.

## Fix
Configure a custom health probe with an explicit, lightweight health
endpoint (e.g., `/healthz`) that returns 200 without requiring
authentication, rather than relying on the default `/` probe against a
path the application was never designed to answer plainly. Set the
probe's Host header explicitly to match what the backend expects --
for App Service, this usually means the exact custom domain or default
hostname the app is configured to respond to, not the backend pool's raw
IP or a mismatched name. Align probe protocol and port with the backend's
actual listener configuration, and size probe timeout/interval/threshold
values to comfortably exceed the backend's real cold-start or
under-load response time rather than the fastest-case response time.
Explicitly allow the gateway's probe source (subnet or documented IP
ranges) through any WAF/NSG rules that might otherwise treat it like
ordinary untrusted traffic.

## Pitfalls
Making the health endpoint too permissive (e.g., always return 200
regardless of actual backend state, such as database connectivity) turns
the probe into a no-op that can't catch real backend degradation --
design the health endpoint to reflect genuine readiness, not just "the
web server process is running." Also, widening probe timeout/threshold
values enough to stop all flapping can mask a real capacity problem (the
backend is actually too slow under load) by simply tolerating slower
responses instead of investigating why they got slow.

## Verify
After correcting the probe configuration, check the Backend health blade
(or Front Door health probe log) and confirm all intended backend members
show Healthy consistently across several probe intervals, not just
momentarily. Send real traffic through the gateway (not directly to the
backend) and confirm 502s are gone. Deliberately trigger a scale-out or
deploy event and watch the health status during that transition to
confirm probe timing tolerances hold up under the realistic worst case,
not just steady state.
