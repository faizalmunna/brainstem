---
name: too-many-tools-degrades-tool-selection
description: An agent given a large number of available tools at once picks the wrong tool more often than when given a small, task-curated subset.
triggers: ["agent performs worse with more tools", "too many tools confuse the model", "tool selection accuracy drops", "should I give the agent every tool", "large toolset hurts performance"]
permissions: ["READ"]
---

## Symptom
As more tools are registered with an agent (often past roughly 15-30,
though the exact point varies by model and how similar the tools are),
measured tool-selection accuracy or task success rate drops compared to
giving the same agent a smaller, curated subset for the same task class
-- even though every added tool is individually well-described and
technically relevant to the domain.

## Likely causes
1. **Every tool definition (name, description, full parameter schema)
   consumes context tokens on every single turn**, whether or not it's
   relevant to the current request -- a large tool list crowds out
   budget that would otherwise hold task-relevant conversation history,
   and increases the surface area the model has to discriminate between.
2. **Increased functional overlap at scale** -- the more tools exist, the
   more likely several of them plausibly apply to a given request (see
   the ambiguous-tool-descriptions skill in this pack), and this problem
   compounds combinatorially rather than linearly as the toolset grows.
3. **Tools relevant to unrelated workflows are always present** -- an
   agent handling customer support tickets that also has database-admin
   or billing-refund tools loaded at all times increases the chance of
   an incorrect but superficially plausible selection for edge-case
   requests.
4. **No routing/staging layer** -- the system exposes the entire tool
   catalog to the model on every turn instead of narrowing it based on
   the task type, conversation stage, or a cheap upfront classification
   step.

## Diagnose
- Measure tool-selection accuracy (correct tool chosen for a labeled set
  of test requests) at different toolset sizes for the same task
  distribution -- plot accuracy against tool count to see whether there's
  a clear inflection point rather than assuming degradation from
  anecdote.
- Check how much of the system prompt's token budget the full tool list
  (names + descriptions + schemas) consumes, and whether trimming it
  measurably frees up budget that improves adherence to other
  instructions.
- For a sample of wrong picks, check whether the correct tool and the
  wrongly-chosen tool are both present in the full list but only one
  would exist in a task-scoped subset -- if so, that's direct evidence
  the extra tools are actively causing the wrong pick, not just adding
  noise.
- Segment failures by task category and check whether they cluster
  around requests where several tools from *different* sub-domains are
  all superficially relevant.

## Fix
Curate the tool list per task/session rather than exposing every
registered tool globally at all times. Group tools by workflow or domain
and load only the subset relevant to the current task type, determined
either by a cheap upfront classification step (a lightweight
intent-detection pass before the main agent loop starts) or by explicit
context (which mode/workflow the session is in). For agents that
genuinely need a very large tool catalog (e.g. hundreds of API
endpoints), use a two-stage pattern: a first call that searches/retrieves
the small number of relevant tool definitions for the current request
(tool retrieval, analogous to RAG for tools), followed by the actual
tool-use turn with only that narrowed set exposed. Keep tool descriptions
concise and avoid re-including tools whose functionality is already
covered by a more general tool in the same session.

## Pitfalls
- Curating the toolset once at agent-design time and never revisiting it
  as more tools get added over months -- toolset bloat is incremental,
  so review tool-selection accuracy periodically, not just at initial
  launch.
- Building a rigid, hardcoded mapping from task type to tool subset that
  breaks the moment a request spans two categories -- prefer a
  retrieval/classification step that can return a union of relevant
  tools over a brittle static lookup table.
- Assuming smaller is always better and cutting the toolset so
  aggressively that the agent lacks a tool it legitimately needs for a
  valid edge case -- validate the curated subset against real historical
  request diversity, not just the common-case requests.

## Verify
Run the same labeled evaluation set of requests through the agent with
the full tool list and with the curated/staged subset, and compare tool-
selection accuracy and end-to-end task success rate side by side --
confirm the curated version matches or beats the full-toolset version,
and separately confirm no previously-handled request category now fails
due to a missing tool in the narrowed set.
