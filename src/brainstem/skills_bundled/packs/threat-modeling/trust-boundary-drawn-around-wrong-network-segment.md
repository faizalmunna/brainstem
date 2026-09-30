---
name: trust-boundary-drawn-around-wrong-network-segment
description: A threat model diagram marks a network segment or internal system as trusted when the real deployment actually exposes it to less-trusted paths, causing threats that cross that boundary to be missed entirely.
triggers: ["the diagram shows this as internal-only but it's actually reachable from the VPN", "we assumed the internal network was trusted", "this threat wasn't caught because we drew the boundary in the wrong place", "is this segment actually trusted"]
permissions: ["READ"]
---

## Symptom
A specific threat (lateral movement, credential replay, a compromised internal service reaching a sensitive data store) turns out, after an incident or a pen test, to have been entirely missed by the threat model — not because no one thought about that threat category, but because the diagram drew a boundary line that labeled the relevant segment "trusted internal network" or "trusted internal service," so nothing crossing into it was ever analyzed as an attack path. The diagram matches how the network was supposed to be segmented on paper, not how it's actually reachable.

## Likely causes
1. **Diagram inherited from an old or intended architecture, not the actual one** — the trust boundary was copied from a reference architecture or an earlier design doc and never validated against the current VPC/subnet/security-group configuration, firewall rules, or VPN routing that actually determines reachability today.
2. **"Internal" used as a proxy for "trusted" without checking who is actually inside** — the boundary assumes internal network = employees only, but in practice contractors, third-party integrations, other business units, or a flat corporate VPN with weak segmentation all sit inside that same "internal" line, each with a different real trust level.
3. **Boundary drawn at the network layer while the actual trust decision happens at the identity/auth layer** — the model treats "on the VPC" as equivalent to "authorized," ignoring that in a zero-trust or service-mesh deployment, network location grants no privilege by itself and the real boundary is the authentication check, which may be missing or misconfigured on the path in question.
4. **Shared infrastructure crossing the assumed boundary** — a shared database, message queue, logging pipeline, or CI/CD runner spans both the "trusted" and "untrusted" sides in reality (e.g., a build agent that can reach both a public-facing staging environment and production secrets), but the diagram shows them as cleanly separated because the shared dependency wasn't traced.

## Diagnose
1. Pick every boundary line in the diagram labeled "trusted," "internal," or "DMZ" and, for each, list the actual set of principals that can reach it today: pull real security-group/firewall-rule/VPC-peering configuration or run a reachability check (e.g., `nmap`/cloud provider's reachability analyzer) rather than relying on the intended design.
2. Cross-reference that reachability list against who the diagram assumes is on that side of the boundary. Any mismatch (a contractor account, a peered VPC from another team, a third-party webhook source) is a mis-drawn boundary.
3. Check whether authentication/authorization is actually enforced at the boundary crossing point, or whether the diagram is using physical/network placement as an implicit stand-in for identity verification — test by attempting an authenticated-vs-unauthenticated request from within the "trusted" segment against the resource in question.
4. Trace every service with access on both sides of a drawn boundary (shared CI runners, shared logging/metrics agents, shared secrets managers) — these are the most common places a boundary is silently bridged.

## Fix
Redraw trust boundaries based on actual, verified reachability and actual authentication enforcement, not on organizational labels like "internal" or "production VPC." For each boundary, write down explicitly who/what is assumed to be on the trusted side and validate that assumption against current infra config as part of the review, not just the initial drawing. Where network location and authorization diverge (increasingly common with VPNs, service meshes, and multi-tenant internal platforms), draw the boundary at the point where identity is actually checked, and treat "same network, no auth" as untrusted-to-untrusted regardless of the network diagram's visual segmentation. Re-verify boundaries whenever network topology changes (new VPC peering, new VPN client population, new third-party integration granted internal network access).

## Pitfalls
A common overcorrection is declaring the entire internal network "untrusted" and modeling every internal call identically to an external one, which produces so many maximum-severity findings that the team can't prioritize real gaps — the goal is accurate boundaries, not maximally paranoid ones. Another pitfall: validating reachability once at model-creation time and treating it as permanent, when VPN client lists, VPC peering, and security groups change continuously and silently re-widen a boundary that was correctly drawn six months ago.

## Verify
For each trust boundary in the model, produce (or re-run) an actual reachability test from outside the assumed-trusted side to a resource inside it, and confirm the result matches the diagram's assumption. Any boundary where a real reachability test contradicts the diagram is a confirmed miss that needs the threat analysis re-run for flows crossing it.
