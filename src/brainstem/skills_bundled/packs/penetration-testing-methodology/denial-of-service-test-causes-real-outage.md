---
name: denial-of-service-test-causes-real-outage
description: A penetration test's availability/DoS testing component causes a real, unintended production outage because it wasn't properly scoped, throttled, or coordinated with the operations team.
triggers: ["pentest caused real outage", "dos testing crashed production", "penetration test took down the service", "availability testing unintended downtime"]
permissions: ["READ"]
---

## Symptom

During a penetration testing engagement that includes availability/
denial-of-service testing as part of its scope, the target system
actually goes down or becomes severely degraded for real users -- an
unintended production outage rather than the controlled,
observation-only assessment of resilience that was presumably intended.

## Likely causes

- **DoS testing was performed directly against a production environment**
  rather than a dedicated, isolated test environment, so any actual
  service degradation caused by the test directly affects real users
  with no isolation.
- **The test wasn't throttled or bounded to a safe intensity level**
  agreed in advance -- "test resilience to load" was interpreted as
  "push until something breaks" without a predefined ceiling coordinated
  with the operations team who understands the system's actual capacity
  limits.
- **Operations/on-call teams weren't informed of the testing window**,
  so when the system did degrade, it was treated as a genuine incident
  (paging on-call, triggering incident response) rather than an
  understood, monitored test activity, compounding the disruption with
  unnecessary incident response overhead.
- **Cascading effects weren't anticipated** -- a test targeting one
  specific service inadvertently overloaded a shared dependency (a
  database, a rate-limited third-party API) that other, out-of-scope
  services also depend on, spreading impact beyond the intended target.

## Diagnose

1. Reconstruct the exact testing activity and timeline against the
   actual outage timeline to confirm the causal link (versus coincidental
   timing).
2. Check the engagement's scope document for what was actually agreed
   regarding availability testing -- environment, intensity limits,
   coordination requirements -- and compare against what was executed.
3. Check whether operations/on-call was informed of the testing window
   in advance, and if so, whether the actual test still exceeded what was
   communicated.
4. Trace the technical cause of the outage to identify whether it was
   the directly-targeted system or a shared dependency that cascaded.

## Fix

Scope availability/DoS testing to a dedicated, isolated test
environment wherever at all possible, rather than production, so any
actual service degradation from the test has zero real-user impact.
Where production testing is genuinely necessary (some availability
characteristics only manifest at real production scale), agree on and
strictly enforce a bounded intensity ceiling in advance, with the
operations team's input on safe limits based on their knowledge of
actual capacity, and require real-time coordination (a live communication
channel) during the test so it can be halted immediately if unexpected
impact appears. Always inform operations/on-call of the testing window
in advance so any observed degradation is correctly understood as
expected test activity, not treated as an unplanned incident.

## Pitfalls

Don't skip availability/DoS testing entirely to avoid this risk --
understanding real resilience limits has genuine security and
reliability value; the fix is proper environment isolation and
coordination, not avoiding this category of testing altogether.

## Verify

For the next engagement including availability testing, confirm it
either runs against an isolated environment or has an explicit,
agreed-upon and monitored intensity ceiling with operations
coordination, and confirm operations/on-call was informed of the testing
window in advance with a way to halt the test if needed.
