---
name: new-feature-shipped-without-threat-modeling-review
description: A new feature or component ships with zero threat modeling because the process only applies to projects formally designated as major, and this one wasn't flagged.
triggers: ["this shipped without any security review", "we didn't threat model this because it wasn't a 'major' project", "how did this feature slip through without a security review", "small feature turned out to have a real security gap"]
permissions: ["READ"]
---

## Symptom
A feature, service, or integration goes to production and, months later, a security review, incident, or pen test finds a threat modeling gap in it — but when the team checks, there was never any threat modeling review at all for that piece of work, because it was never classified as a "major project" requiring one. It was a "small" addition, an internal tool, a quick integration, or built by a team that doesn't normally trigger the security review gate, so it fell through a categorical exclusion rather than through an oversight within a review that happened.

## Likely causes
1. **The threat modeling process only triggers on project-management signals** (size of the initiative, whether it went through a formal architecture review board, whether it's customer-facing) that don't reliably correlate with actual security relevance — a "small" internal admin tool can have full production database access, while a "major" customer-facing feature might be a thin UI layer over already-reviewed infrastructure.
2. **No default-on policy** — the process is opt-in ("flag your project for a threat model if you think it needs one") rather than opt-out, so it depends on the team building the feature correctly self-assessing its own risk, which is exactly the judgment call the process exists to backstop in the first place.
3. **Classification happens once, early, and doesn't get revisited as scope grows** — a project starts as a genuinely minor prototype exempt from review, then quietly grows in scope (more data access, more integrations, wider exposure) without anyone re-evaluating whether it still qualifies as "minor."
4. **Review capacity constraints drive the threshold, not risk** — the security team can only run N full threat-modeling sessions per quarter, so the "major projects only" line is really a capacity-rationing mechanism dressed up as a risk-based one, and that pressure quietly excludes things that are risky but not urgent-feeling.

## Diagnose
1. Pull the criteria currently used to decide what gets threat modeled and check whether any of them reference actual risk factors (data sensitivity, access level granted, external exposure, authentication changes) versus only project-management metadata (team size, roadmap tier, whether it has a PRD).
2. Audit a sample of recently shipped features that were *not* threat modeled and check what data access or external exposure each one actually has. If any of them touch sensitive data, cross a trust boundary, or introduce new authentication/authorization logic, the classification threshold is missing real risk signals.
3. Check whether there's a lightweight self-assessment step (even a five-question checklist) required before a project is exempted, or whether exemption is simply the default with no active decision recorded — an undocumented default-exempt state means nothing is actually filtering for risk.
4. Look at how many projects have grown in scope after being classified "minor" without a re-classification checkpoint — evidence of scope creep past an initial exemption decision.

## Fix
Replace a coarse "major projects only" gate with a lightweight, mandatory risk-triage checklist applied to every new feature or component regardless of perceived size — a handful of yes/no questions (does this touch PII or credentials, does it cross a trust boundary, does it introduce a new external integration or new auth path, does it get elevated data access) that takes minutes, not hours, and routes only the ones that trip a threshold into a full threat-modeling session. This makes the exemption a documented, risk-based decision rather than a default nobody actively chose, and keeps the expensive full workshop reserved for things that actually warrant it rather than being either universally skipped or unsustainably applied to everything. Re-run the triage checklist when a project's scope changes materially (new data types, new integrations, elevated permissions), not just once at kickoff.

## Pitfalls
Making the triage checklist itself heavyweight recreates the original problem — if answering the five questions takes as long as the thing it's supposed to filter for, teams will route around it or answer it carelessly to get through faster. Also avoid tying the triage exclusively to a project-tracking tool that not all teams use (e.g., only projects that go through a specific roadmap process get triaged) — the checklist needs to be attached to the actual mechanism by which code reaches production (PR template, deployment pipeline gate) so it can't be bypassed simply by not filing the paperwork that would have triggered it.

## Verify
Sample the last quarter's shipped features or new services and confirm each one has a recorded triage decision (either "exempted, here's why" or "full review completed") — not silence. Any shipped feature with sensitive data access or new external exposure and no triage record at all confirms the gate is still being bypassed rather than fixed.
