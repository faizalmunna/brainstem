---
name: threat-modeling-excludes-developers
description: Threat modeling is run entirely by a separate security team without the implementing developers in the room, so the resulting threats miss implementation details only the developers actually know.
triggers: ["security ran a threat model workshop without us", "the threat model doesn't match how we actually built this", "developers weren't invited to the threat modeling session", "security team threat modeled our service based on the design doc only"]
permissions: ["READ"]
---

## Symptom
A threat model exists, produced by a security or risk team, and looks thorough on paper, but when developers who actually built the system read it, they immediately spot gaps: it assumes an authentication check happens somewhere it doesn't, it models a data flow that was changed during implementation and never updated in the design doc, or it misses an internal debug endpoint, a fallback code path, or a third-party SDK call that only shows up in the actual code, not the architecture diagram. The findings that do exist tend to be generic (default OWASP-category threats) rather than specific to how this particular system was actually built.

## Likely causes
1. **Threat modeling scheduled from the design doc, before or disconnected from implementation** — the session happens once, early, based on the intended architecture, and the developers who later make implementation trade-offs (an added caching layer, a debug bypass, a shortcut around a planned validation step) are never looped back in to flag that those trade-offs changed the threat surface.
2. **Organizational split treats security as a gate, not a collaborator** — threat modeling is scoped as something the security team does *to* a project (a checkbox for approval) rather than *with* the team building it, so there's no expectation that developers attend, contribute, or even review the output.
3. **Developers assume it's not their job** — even when invited, developers may treat the session as security's domain and stay passive, contributing diagram corrections but not surfacing the kind of "here's a weird edge case in how we actually implemented the retry logic" detail that only surfaces from someone who wrote the code.
4. **No mechanism to feed implementation reality back into the model** — even if developers know something has diverged from the modeled design, there's no lightweight path (a comment thread, a required field in the PR template) for that discrepancy to reach whoever owns the threat model document.

## Diagnose
1. Check who is listed as an attendee or contributor on the threat model document's history — if it's exclusively security/risk team members with no engineer from the team that owns the system, that's the direct signal.
2. Pick two or three implementation details that only exist in code (a specific retry/fallback path, an internal admin endpoint, a feature flag that bypasses a check in some environments) and check whether any of them appear in the threat model. Their absence, especially when they're clearly security-relevant, indicates the model was built from the design doc rather than the real system.
3. Ask a developer on the team to review the current threat model for five minutes and note discrepancies with actual behavior — in practice this reliably surfaces at least one gap when developers were excluded from the original session.
4. Check whether the threat model references specific function names, endpoint paths, or config flags (implementation-level detail) versus only component-level boxes and arrows (design-level detail only) — an implementation-blind model stays entirely at the box-and-arrow level.

## Fix
Make the people who write and maintain the code mandatory participants in threat modeling for their own systems, not optional reviewers of someone else's output. Structure the session so developers are asked directly about deviations from the design ("where does the real implementation differ from this diagram," "what's the ugliest workaround in this code path," "what happens when this external call times out or is rate-limited") rather than only validating the security team's pre-drawn diagram. Give the security team a facilitation role (bringing the STRIDE framework, threat categories, and outside perspective) while developers supply the ground truth about actual behavior — the combination catches both the threats a security specialist would think to ask about and the ones only visible from inside the implementation.

## Pitfalls
Simply inviting developers to a meeting they don't feel ownership of doesn't fix this — if attendance is nominal (they show up, stay quiet, defer to security's framing) the underlying gap persists despite the invite being sent. The fix requires developers to be asked pointed, implementation-specific questions during the session, not just given a seat. A related pitfall: over-correcting into "developers self-threat-model with no security involvement," which loses the systematic framework (STRIDE categories, awareness of attack patterns outside the team's own experience) that a security specialist contributes — the goal is collaboration, not a handoff in either direction.

## Verify
For the next threat modeling session on a given system, confirm at least one threat in the resulting document traces directly to an implementation detail (a specific code path, config flag, or edge case) that could only have come from someone who wrote or maintains the code, not from the architecture diagram alone.
