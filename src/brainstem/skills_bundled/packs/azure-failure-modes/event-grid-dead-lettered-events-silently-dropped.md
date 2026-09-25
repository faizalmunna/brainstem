---
name: event-grid-dead-lettered-events-silently-dropped
description: A Logic App or Function triggered by an Event Grid subscription silently misses events because retries exhausted and dead-lettering wasn't configured or monitored.
triggers: ["event grid missing events no error", "logic app not triggering for some events", "event grid retries exhausted events lost", "azure function event grid trigger silently drops messages"]
permissions: ["READ"]
---

## Symptom
A Logic App or Azure Function subscribed to an Event Grid topic processes
most events normally, but some events never arrive at the handler at all
-- no error surfaces anywhere in the handler's own logs, because from the
handler's perspective those events simply never existed. The publisher
(the source emitting events) shows no indication of a problem either.

## Likely causes
1. **The event subscription has no dead-letter destination configured**,
   so when delivery to the endpoint fails repeatedly (endpoint down,
   returning errors, or timing out) past Event Grid's retry policy, the
   event is dropped entirely with nothing durable retained anywhere --
   Event Grid does not dead-letter by default; it has to be explicitly
   configured with a Storage Account destination.
2. **A dead-letter destination is configured, but nobody monitors it** --
   events are landing in the dead-letter Storage container exactly as
   designed, but without an alert or a regular process consuming that
   container, the events are effectively lost in practice even though
   they're technically retained (subject to the storage container's own
   retention).
3. **The retry policy's `maxDeliveryAttempts` and `eventTimeToLiveInHours`
   are shorter than the handler's realistic recovery time** -- e.g., set
   to the defaults or tightened for cost/latency reasons, so a transient
   outage in the handler (a deploy, a brief scale-to-zero cold start
   delay, a downstream dependency blip) that lasts longer than the retry
   window exhausts retries and dead-letters/drops events that would have
   succeeded on one more attempt.
4. **The handler returns a 2xx response for a request it actually failed
   to process** (e.g., an exception thrown after the response was already
   sent, or an Azure Function trigger acknowledging receipt before
   completing processing), which Event Grid interprets as successful
   delivery -- it will never retry or dead-letter something it believes
   already succeeded, so the loss looks identical to a "why didn't this
   fire" mystery rather than a retry-exhaustion one.
5. **The event subscription's filter (subject filter, event type filter,
   or advanced filter) is narrower than intended**, silently excluding a
   category of events from ever being delivered in the first place --
   distinct from a delivery failure, this is filtered-out-at-source and
   won't appear in dead-letter storage either, since Event Grid never
   attempted delivery for events that didn't match the filter.

## Diagnose
- Check the Event Grid subscription's configuration for a **Dead-letter
  destination** (Storage Account + container) -- if none is configured,
  that alone explains silent loss for any delivery failure, independent
  of any other cause.
- If dead-lettering is configured, list the contents of the dead-letter
  container for the time window when events went missing -- their
  presence confirms delivery-failure-and-exhausted-retries as the cause,
  and the stored event payload plus the `deadLetterReason` metadata
  explains why (e.g., an endpoint error code history).
- Check Azure Monitor metrics for the Event Grid topic/subscription:
  **Delivery Attempt Failed**, **Publish Succeeded**, and **Matched Event
  Count** -- comparing matched events against successfully delivered
  events for the affected time window isolates whether events were
  filtered out, failed delivery, or never published at all.
- Review the event subscription's filter configuration (`az eventgrid
  event-subscription show --query filter`) against the specific event
  type/subject of a missing event to rule out filter exclusion before
  assuming a delivery failure.
- Check the handler's own logs (Function/Logic App run history) around
  the retry window for evidence of a transient outage (cold start,
  deployment, exception after response) that would explain exhausted
  retries, and specifically check for any code path that could return
  success before processing actually completed.

## Fix
Configure a dead-letter destination on every Event Grid subscription that
matters operationally, as a baseline, not an afterthought added after a
loss incident. Pair it with an actual alert (Azure Monitor alert rule on
blob-created events in the dead-letter container, or a scheduled
Function/Logic App that periodically drains and reprocesses or reports on
it) so dead-lettered events are visibly triaged rather than silently
retained. Size `maxDeliveryAttempts`/`eventTimeToLiveInHours` to
comfortably exceed the handler's realistic recovery time for known
transient failure modes (a typical deploy duration, a downstream
dependency's usual blip length), and make the handler's success/failure
semantics precise -- only acknowledge/return success after processing has
actually completed and durably succeeded, so Event Grid's retry mechanism
can do its job on genuine failures instead of being told everything
succeeded.

## Pitfalls
Setting `maxDeliveryAttempts` very high or `eventTimeToLiveInHours` very
long to "never lose an event" can mask a persistently broken handler
behind seemingly-eventual delivery, while also delaying dead-letter
visibility for genuinely permanent failures far longer than useful for
incident response -- tune retry generosity to real transient-failure
durations, not to infinity. Also, building a dead-letter *destination*
without a consumption/alerting process for it gives a false sense of
safety ("we have dead-lettering configured") while events pile up
unnoticed indefinitely.

## Verify
Deliberately fail a test endpoint (return errors or take it offline
briefly) and confirm the affected test event appears in the dead-letter
container with a `deadLetterReason` after retries exhaust, and that the
configured alert fires. Then restore the endpoint and confirm normal
events resume flowing and being matched by the subscription's filter as
expected. Review Azure Monitor's Matched Event Count vs. Delivery
Succeeded metrics over a subsequent period to confirm no silent gap
reopens.
