---
name: threat-model-stale-after-architecture-changed
description: A threat model was drawn once during initial design and never updated, so it silently omits threats introduced by every architectural change made since.
triggers: ["our threat model is out of date", "the diagram doesn't match production anymore", "do we need to update the threat model after this change", "threat model from the original design doc"]
permissions: ["READ"]
---

## Symptom
A threat model document (or diagram) exists, was clearly produced once with real effort, but references components that were since removed, is missing components added in the last several releases, or still shows a data flow that no longer matches how the system is deployed. When someone asks "is this new integration covered by the threat model," the honest answer is nobody knows, because nobody has looked at the document since it was created.

## Likely causes
1. **No trigger process** — threat modeling was scoped as a one-time deliverable for initial design sign-off, with no policy defining what kind of change ("added an external API," "introduced a new trust boundary," "added a third-party integration") should trigger a re-review.
2. **Ownership vacuum** — the person or team who built the original model moved to a different project, and updating it was never assigned to whoever owns the system now, so it just doesn't happen by default.
3. **Cost mismatch** — updating the model is treated as a full re-run of the original workshop (hours of cross-team time), so it feels too expensive to do incrementally for a "small" change, and small changes accumulate into a large drift.
4. **No link between the model and the codebase/architecture docs** — the threat model lives in a wiki or slide deck disconnected from the architecture-decision-record (ADR) or system-design doc process, so architecture changes don't naturally surface "update the threat model" as a checklist item.

## Diagnose
1. Pull the threat model's last-modified date and diff the list of components/data flows it documents against the current architecture diagram or service catalog (e.g., current Terraform/K8s manifests, current API gateway routes). List anything present in one but not the other.
2. Check version control or wiki history for the threat model file itself — if the last substantive edit predates the last N architecture-impacting PRs (new service, new external dependency, new auth flow), that's a direct staleness measurement.
3. Search recent ADRs or design docs for the phrase "threat model" — if none of the last several architecture changes mention it, there's no habitual trigger.
4. Ask whoever owns the current on-call rotation whether they know the threat model exists and where it lives — if they don't, it has decayed into a historical artifact rather than a living reference.

## Fix
Treat the threat model as a living artifact with an explicit re-review trigger, not a one-time deliverable. Define a short, concrete list of change types that require a scoped (not full) re-review: new external-facing endpoint, new trust boundary (new deployment environment, new third-party integration, new data store crossing a compliance boundary), new authentication/authorization mechanism, or a new class of data being processed. Wire that trigger into the existing change process (ADR template, PR template for infra changes, or design-review checklist) so it's asked automatically rather than relying on someone remembering. Keep the model itself in the same repo as the architecture docs it describes, versioned alongside code, so drift is visible in diffs rather than requiring a separate audit.

## Pitfalls
Re-running the entire original multi-hour STRIDE workshop for every minor change makes updates so expensive that they get skipped anyway — the fix is a lightweight, scoped delta review (just the new/changed component and its immediate trust boundaries), not a full repeat. Also avoid the opposite failure of updating the diagram's shapes without re-asking "what changed about who can reach this and what happens if it's compromised" — a cosmetically current diagram that never re-examines threats is just as stale in substance.

## Verify
Pick the three most recent architecture-impacting changes (new service, new integration, or new environment) and confirm each one has a corresponding entry or diff in the threat model dated at or after that change's merge date. If any of the three is missing, the update trigger isn't actually firing yet.
