---
name: canary-upgrade-green-then-fails-on-mixed-version-interop
description: A dependency upgrade passes a staged canary rollout with a clean error rate, then breaks on full rollout specifically because the new and old versions cannot safely inter-operate while both are live.
triggers: ["canary passed but full rollout broke", "new version breaks only when talking to old version", "rolling upgrade mixed versions incompatible", "deploy split by version and only old-to-new traffic fails"]
permissions: ["READ"]
---

## Symptom

The dependency upgrade is rolled out gradually -- a canary batch of hosts,
a percentage of traffic first. The canary shows a clean error rate, so the
rollout proceeds to full. On full rollout, incidents appear that the
canary never surfaced: failures on requests or messages that cross a
version boundary (an old host calling a new host, a queued job whose
payload format changed). The upgrade was only incompatible between the new
version and the *old* version, not with itself, and the canary was green
because its traffic was almost entirely new-to-new.

## Likely causes

- **The incompatibility is cross-version, not single-version:** the new
  version changes a wire format, a stored message shape, a hashing/partitioning
  scheme, or an RPC contract that only breaks when one side is old and the
  other is new.
- **Canary routing kept incompatible traffic away from the new version:**
  session affinity, fan-out rules, or a load split pinned a session to
  whichever version handled it first, so new hosts only ever talked to new
  hosts and the canary never produced a mixed pair.
- **Version negotiation is asymmetric or absent:** the new side can read
  old-format data (or claims it can), but the reverse direction breaks,
  and a canary that only sends new-to-new traffic never exercises it.
- **The upgrade promoted shared state along with the code** (a cache/queue/
  schema format, migrated config) that cannot be reverted independently,
  so the "canary" gated only the binary and not the data it depends on.

## Diagnose

1. Replay the failing request or message pattern with old and new hosts
   forced onto opposite ends -- explicit old-to-new and new-to-old test
   cases, not whatever mix the canary happened to receive.
2. Check the dependency's upgrade notes for wire-format, serialization, or
   cross-version changes; those are the classic mixed-version breakers.
3. Inspect the canary's routing for whether a mixed-version pair ever
   actually occurred: go through affinity and fan-out rules and ask whether
   old-to-new traffic was routed anywhere in the canary window.
4. Grep the dependency's protocol/handshake code path for what it does
   when the peer's advertised version list disagrees with its own.

## Fix

Treat any upgrade that can change a wire format, a persisted data shape, or
a cross-host behavior as requiring an explicit mixed-version interop test
before full rollout: run a scripted matrix (old-to-old, old-to-new,
new-to-old, and new-to-new where the dependency supports rolling upgrades)
and deliberately route reverse-boundary traffic -- old clients to new
instances -- at the canary stage instead of relying on natural traffic.
If the dependency has no rolling-upgrade story at all (documented
incompatibility between adjacent versions), plan the rollout as a
fleet-wide coordinated cutover in a maintenance window, with code, data,
and config promoted together, rather than a gradual percentage that
guarantees a long mixed-version period.

## Pitfalls

Don't take "the error banner stayed quiet in the canary" as proof of
compatibility -- a canary only validates the traffic patterns the load
balancer happened to send it. If no old-to-new pair occurred in the canary
window, the canary tested nothing about the actual cross-version risk, and
"it was green" is a statement about routing, not about the upgrade.

## Verify

Before declaring the rollout complete, confirm the documented mixed-version
matrix (old-to-new and new-to-old, in both directions where applicable)
passes against the real deployment, and confirm the canary config now
explicitly routes at least some cross-boundary traffic through the new
version while the old version is still live -- so a future mixed-version
incompatibility fails in the canary, not at full rollout.