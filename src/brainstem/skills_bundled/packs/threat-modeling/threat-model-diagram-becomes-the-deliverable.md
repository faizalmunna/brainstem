---
name: threat-model-diagram-becomes-the-deliverable
description: The team treats a polished threat modeling diagram or document as the finished output, with identified mitigations never actually making it into a tracked engineering backlog.
triggers: ["we have a beautiful threat model doc but nothing got fixed", "the diagram was the deliverable for the audit", "we spent weeks on the threat modeling doc and none of it turned into work", "the threat model exists purely to satisfy compliance"]
permissions: ["READ"]
---

## Symptom
A threat modeling exercise produces a genuinely well-made artifact — a detailed data-flow diagram, a thorough STRIDE table, maybe even a polished slide deck presented to leadership or an auditor — and everyone treats that artifact's existence as success. It gets filed, referenced in compliance documentation, and cited when someone asks "do we do threat modeling here." But when you check whether any of the mitigations it recommends were implemented, the answer is few or none; the diagram was the finish line, not a step toward one.

## Likely causes
1. **The exercise is scoped and resourced as a documentation task, driven by a compliance or audit deadline**, so success is defined as "the document exists and was reviewed by the required date," and once that box is checked, the organizational attention that produced it moves on to the next deadline rather than to implementation.
2. **No handoff mechanism between the threat modeling artifact and engineering planning** — the people who write the threat model (security, architecture) and the people who prioritize and schedule engineering work (product, engineering leads) operate in separate planning processes with no required step connecting the two, so a finding has nowhere to go by default.
3. **Diagram quality becomes a proxy for thoroughness, and thoroughness becomes a proxy for effectiveness** — a visually impressive, detailed diagram feels like it represents real security rigor, which can substitute, in perception, for the harder and less visible work of actually closing the gaps it identifies.
4. **Findings are phrased at a level too abstract to become a ticket** — "improve input validation across the service" or "review authentication architecture" reads like a completed analytical finding but isn't actionable as-is, so it never gets picked up by an engineer looking for a scoped, ticket-sized piece of work, and nobody does the additional translation step.

## Diagnose
1. Take the most recent threat model document and count how many of its findings/recommended mitigations have a corresponding entry in the engineering backlog (ticket, story, or task) that is either completed or actively in progress. A near-zero conversion rate is the direct signal.
2. Check what the threat modeling exercise's due date was tied to — if it maps to an audit, certification renewal, or compliance deadline and nothing else, that's a sign the artifact's existence, not its follow-through, is what's actually being measured.
3. Read a handful of findings verbatim and ask whether an engineer could pick one up and start work without further scoping. If findings read as broad recommendations rather than specific, boundable tasks, that's why they never convert into tickets.
4. Ask engineering leadership directly whether they've seen the threat model document and whether any of its content shows up in current sprint or roadmap planning. A "no" to either confirms the disconnect.

## Fix
Require that every threat modeling exercise end with each finding translated into a specific, scoped backlog item — with an owner and target timeframe, as covered by ownership/follow-through practice — before the exercise is considered complete, not as an optional next step someone might get to. Rewrite abstract findings into concrete, boundable engineering tasks as part of the exercise itself (turn "review authentication architecture" into "add rate limiting to the password-reset endpoint" and "require re-authentication for the admin API's permission-change action"), since translating vague findings into actionable tickets is real analytical work that shouldn't be left implicit. Redefine what "done" means for the exercise: not "the document was published and reviewed," but "the document was published and every finding above the priority threshold has a live ticket," making the backlog conversion itself the measured deliverable rather than the diagram.

## Pitfalls
A common shortcut is dumping every finding into the backlog verbatim and calling that "done" — a ticket with no realistic scoping or priority just relocates the problem from a static document to a backlog graveyard where it's equally unlikely to get worked. The translation step (making findings concrete and appropriately prioritized against other engineering work) has to be real, not just a change of medium. Also watch for treating "presented to leadership/passed the audit" as the success signal for the exercise — audits and compliance checks generally verify that a process happened and a document exists, not that the underlying risk was reduced, so passing one is not evidence the threat modeling actually worked.

## Verify
For the current threat model, confirm that every finding at or above the agreed priority threshold has a linked, appropriately-scoped ticket in the real engineering backlog, and sample two or three of those tickets to confirm they're specific enough that an engineer could start work on them without needing to re-derive what the finding actually meant.
