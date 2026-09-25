---
name: threat-list-generated-without-prioritization
description: A threat modeling session produces dozens of theoretical threats in a spreadsheet but no ranking, so the team cannot tell which ones actually deserve mitigation work.
triggers: ["we have 60 threats and no idea where to start", "the threat model spreadsheet just keeps growing", "which of these threats actually matter", "STRIDE workshop produced a huge list with no next steps"]
permissions: ["READ"]
---

## Symptom
After a STRIDE (or similar) workshop, there's a spreadsheet or ticket list with 40-100+ rows, each a plausible-sounding threat ("attacker spoofs internal service identity," "log data could be tampered with in transit"), but no severity, no likelihood estimate, and no ordering. Engineers look at the list, feel overwhelmed, and either mitigate the first few threats someone happened to type at the top or ignore the list entirely because "everything on it is theoretically true."

## Likely causes
1. **Workshop optimized for coverage, not decision-making** — the facilitation method (e.g., going category-by-category through STRIDE for every component) rewards enumerating every conceivable threat but has no built-in step for scoring, so the output is a brainstorm artifact mistaken for a finished deliverable.
2. **No shared risk model** — the team has never agreed on what "likelihood" and "impact" mean for their system (no defined scale, no reference to actual asset value or blast radius), so even if someone tried to rank threats, there's no consistent basis to do it, and ranking gets skipped as "too subjective."
3. **Fear of looking like they're dismissing security work** — whoever ran the session is reluctant to explicitly mark threats as low-priority because it can look like downplaying risk to auditors or leadership, so everything stays formally "open" and unranked to avoid that appearance.
4. **Tooling produces a flat list by default** — some threat-modeling tools (auto-generated STRIDE-per-data-flow output) dump every combinatorial threat without an integrated scoring step, and teams ship that raw export as the final artifact instead of treating it as an intermediate one.

## Diagnose
1. Open the threat list and check for a severity/likelihood/risk-score column. If it's absent, or present but empty/uniform (everything marked "Medium"), prioritization never actually happened.
2. Ask the team to name the top 3 threats from the list from memory. If they can't, the list isn't functioning as a decision tool — it's inventory, not intelligence.
3. Check whether any threat from the list has ever been converted into a scheduled engineering ticket. If the conversion rate is near zero across the whole list, the absence of prioritization is likely why — there's no signal for which ones warrant that step.
4. Look for a scoring rubric (DREAD, CVSS-adjacent, or a custom likelihood x impact matrix) referenced anywhere in the team's docs. If none exists, there's no shared basis to rank against, confirming root cause 2.

## Fix
Add a mandatory scoring pass as a second phase of the exercise, separate from and after threat enumeration — don't try to score threats live in the same discussion where they're being generated, since brainstorming and judging use different modes of thinking and mixing them suppresses both. Use a simple, consistent rubric (e.g., likelihood and impact each rated low/medium/high against concrete anchors specific to the system — "high impact" defined as "customer PII exposed" or "production write access," not left abstract) so scoring doesn't require re-litigating definitions every time. Sort the final list by the resulting risk tier and only carry forward the top tier (plus anything flagged as trivial-to-fix regardless of tier) into actual backlog tickets; explicitly document the lower-tier threats as "identified, accepted at current priority" rather than silently dropping them, so the decision is visible and defensible later.

## Pitfalls
A common overcorrection is inventing an elaborate scoring formula (weighted multi-factor DREAD-style math) that takes as long to apply as the original brainstorm and produces false precision — a coarse 3x3 or 2x2 matrix that a team can apply consistently is more useful than a sophisticated one nobody trusts or maintains. Another pitfall: scoring threats by how interesting or novel the attack sounds rather than by actual likelihood given the real deployment (an exotic timing side-channel scored above a plainly reachable auth bypass) — anchor likelihood to how the system is actually deployed and who can actually reach the relevant boundary, not to how clever the described attack is.

## Verify
Confirm every threat on the current list has a non-empty, non-uniform severity/priority field, and that the top-ranked 5-10 threats each have a corresponding ticket or an explicit documented acceptance decision with an owner's name attached — not just a priority label with no next action.
