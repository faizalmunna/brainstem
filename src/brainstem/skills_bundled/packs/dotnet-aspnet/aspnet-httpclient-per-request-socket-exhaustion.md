---
name: aspnet-httpclient-per-request-socket-exhaustion
description: Diagnose an ASP.NET service that exhausts sockets or fails outbound HTTP calls under sustained load from creating a new HttpClient per request.
triggers: ["socketexception address already in use", "too many open files outbound http", "httpclient causing port exhaustion", "new httpclient() every request", "outbound requests fail under load but work fine at low traffic"]
permissions: ["READ"]
---

## Symptom
Outbound HTTP calls from an ASP.NET service start failing under
sustained or bursty load with errors like
`SocketException: An operation on a socket could not be performed
because the system lacked sufficient buffer space` or connection
timeouts to a downstream service that is otherwise healthy, while the
same code works fine at low traffic or in local testing. `netstat` on the
host shows a large number of connections stuck in `TIME_WAIT` to the same
downstream host/port. The code pattern is almost always `new
HttpClient()` (or `using var client = new HttpClient()`) created fresh
inside the request handler or the method making the call.

## Likely causes
1. **A new `HttpClient` instance is constructed per request (or per
   call) instead of being reused** -- each `HttpClient` owns its own
   connection pool, so creating one per request means connections are
   never pooled/reused across requests; combined with `using` disposing
   the client (and its underlying handler) after every call, the
   underlying TCP connections go through full close/`TIME_WAIT` cycles
   far more often than necessary, exhausting available ephemeral ports
   under load.
2. **`HttpClient` is made a `static`/singleton field as a quick fix, but
   DNS changes for the downstream host are never picked up** -- this
   isn't the socket-exhaustion symptom but the flip side: a single
   long-lived `HttpClient`'s underlying handler caches a DNS resolution
   for the lifetime of the process, so if the downstream service's IP
   changes (common behind a load balancer or during failover), the app
   keeps connecting to a stale address until restarted.
3. **`IHttpClientFactory` is registered but a named/typed client is still
   being manually `new`'d somewhere** -- e.g. a helper class or a legacy
   code path bypasses the factory and constructs `HttpClient` directly,
   so part of the codebase gets pooling and part doesn't, making the
   exhaustion intermittent and harder to trace to a single cause.
4. **A message handler chain (e.g. a custom `DelegatingHandler` for auth
   or logging) is itself instantiated per request and never disposed
   properly**, holding onto its own resources per call even if the outer
   `HttpClient` usage looks correct.

## Diagnose
- Grep the codebase for `new HttpClient(` -- any hit outside of
  `IHttpClientFactory` registration/configuration code (e.g. inside
  `Program.cs`'s `AddHttpClient` calls, which is fine) is a candidate.
- On the affected host during/after an incident, run `netstat -ano` (or
  `ss -tan` on Linux) and count connections in `TIME_WAIT` to the
  downstream host's IP/port -- a very large count correlated with request
  volume confirms socket churn from non-pooled clients rather than a
  downstream-side problem.
- Check whether `IHttpClientFactory` (`AddHttpClient()`/
  `AddHttpClient<TClient>()`) is registered in DI at all; if it is, check
  whether the failing call site actually resolves its client from the
  factory (constructor-injected `HttpClient`/`IHttpClientFactory`) versus
  constructing one directly.
- If a static/singleton `HttpClient` is already in use and the symptom is
  connection failures to a specific host after a failover event (not
  socket exhaustion), check application logs for the timing of the
  downstream's last known IP change versus when failures started --
  consistent staleness starting right after a DNS change points to the
  stale-DNS variant instead.

## Fix
- Register HTTP clients through `IHttpClientFactory`
  (`builder.Services.AddHttpClient("name")` or a typed client
  `AddHttpClient<IMyClient, MyClient>()`), and resolve clients from the
  factory (or via constructor injection of the typed client) instead of
  constructing `HttpClient` directly anywhere in request-handling code --
  the factory manages an internal pool of `HttpMessageHandler`s, rotating
  them on a timer (default 2 minutes) so connections are reused within
  that window but DNS changes are still eventually picked up.
- If a single static `HttpClient` is currently used to work around socket
  exhaustion, migrate it to `IHttpClientFactory` rather than keeping the
  static instance -- the factory gives pooling *and* handles DNS rotation,
  which a bare static client doesn't.
- Route any custom `DelegatingHandler`s (auth token injection, logging,
  retry policies via Polly) through `AddHttpMessageHandler()` on the
  factory registration, so they participate in the same managed handler
  lifecycle instead of being instantiated ad hoc per call.

## Pitfalls
- Fixing socket exhaustion by switching to one `static readonly
  HttpClient` field without going through `IHttpClientFactory`
  reintroduces the stale-DNS problem (cause 2) -- it trades one incident
  type for another; use the factory, not a hand-rolled static instance,
  unless you also implement your own handler rotation.
- Setting the factory's handler lifetime (`SetHandlerLifetime`) extremely
  high "to reduce overhead" reduces DNS responsiveness the same way a
  static client would; the default rotation window exists specifically to
  balance connection reuse against picking up endpoint changes -- don't
  disable it without a specific reason and a compensating control.

## Verify
Under a sustained load test hitting the endpoint that makes the outbound
call, monitor `TIME_WAIT` connection counts to the downstream host before
and after switching to `IHttpClientFactory` -- confirm the count stays
bounded and roughly stable under sustained load after the fix rather than
climbing with request volume, and confirm outbound calls continue
succeeding for the duration of a load test long enough to span at least
one handler-rotation interval.
