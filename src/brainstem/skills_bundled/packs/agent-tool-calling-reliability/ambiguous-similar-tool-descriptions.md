---
name: ambiguous-similar-tool-descriptions
description: An agent inconsistently picks the wrong one of two similar-sounding tools because their descriptions don't clearly distinguish when each applies.
triggers: ["agent picks the wrong tool", "model confuses two similar tools", "inconsistent tool selection", "wrong search tool used", "agent alternates between two tools randomly"]
permissions: ["READ"]
---

## Symptom
The agent has two (or more) tools that overlap in purpose -- e.g.
`search_docs` and `search_knowledge_base`, or `update_ticket` and
`update_ticket_status` -- and across otherwise-similar requests it picks
inconsistently between them, sometimes correctly and sometimes not, with
no clear pattern tied to the actual task difference between the tools.
Fixing one bad call by prompting harder doesn't help because the next
similar request may pick the other tool.

## Likely causes
1. **The tool descriptions describe what each tool does but not when to
   prefer it over its sibling** -- both read like generically reasonable
   choices for the same class of request, so the model has no
   discriminating signal beyond surface wording similarity to the user's
   phrasing.
2. **Genuine functional overlap** -- the tools actually do overlapping
   things (both can technically satisfy many of the same requests) and
   the "correct" choice depends on a business rule (which one is
   authoritative, which one is cheaper/faster, which one has side
   effects) that isn't captured in either description.
3. **The tools were added at different times by different people** without
   reviewing the full tool list for overlap, so naming and description
   conventions drifted and nothing forces a comparison against existing
   tools before adding a new one.
4. **Order/position in the tool list biases selection** -- some models
   show a mild preference correlated with a tool's position in a long
   tool list, which surfaces as apparently "random" inconsistency that's
   actually a list-ordering artifact rather than a description problem.

## Diagnose
- Pull several transcripts where the wrong tool was picked and check
  whether the two tools' descriptions, read side by side, actually give
  a human enough information to know which one is correct for that
  request -- if a human can't tell either, the model can't be expected
  to.
- Check whether the "right" choice depends on information the tool
  description never states (e.g. "use X for anything customer-facing,
  use Y only for internal audits") -- that's a missing-disambiguation
  bug, not a model capability issue.
- Test both tools' descriptions in isolation (temporarily hide one from
  the tool list) and see if the remaining tool is used correctly for all
  the same requests -- confirms the tools are functionally
  interchangeable enough that the model isn't wrong, just under-
  specified about which is preferred.
- Check the tool list ordering and try moving the less-preferred tool
  earlier/later to see if selection frequency shifts independent of the
  request content -- if it does, position bias is contributing.

## Fix
Write each tool's description to include an explicit "use this when...
/ do not use this for... (use `other_tool` instead)" contrast, not just a
standalone description of its own function -- disambiguation is a
property of the pair, not of either tool alone. Where the distinction is
a business rule (authoritative source, cost, side effects, scope), state
that rule directly in both tools' descriptions symmetrically, so whichever
tool the model considers first, it sees the same steering logic. If the
overlap is because the tools are near-duplicates that arose from
organic growth, consider consolidating them into one tool with a
parameter that captures the distinction (e.g. one `search` tool with a
`source` enum) instead of maintaining two separate tools that require the
model to make the source decision implicitly. When consolidation isn't
possible, add a lightweight tool-selection check in the system prompt or
a routing step that resolves the ambiguity before the model even sees
both options for borderline cases.

## Pitfalls
- Writing the disambiguation into only one of the two tools' descriptions
  -- the model may examine either tool first depending on context, so
  the contrast needs to be legible from both sides, not just the one you
  happened to edit.
- Over-consolidating distinct tools into one overloaded tool with many
  parameters "just in case," which trades one ambiguity (which tool) for
  another (which parameter combination) -- consolidate only when the
  tools are genuinely doing the same underlying operation.
- Treating a single wrong pick as evidence of a description problem
  without checking multiple examples -- occasional mispicks on genuinely
  ambiguous edge-case requests are expected even with a good
  description; look for a consistent, systematic pattern before
  rewriting.

## Verify
Rewrite both tools' descriptions with explicit contrastive guidance,
then replay the same set of requests that previously produced
inconsistent picks and confirm the correct tool is chosen consistently
across repeated runs (not just once) -- ideally across a batch of
paraphrased variants of each request, not just the exact original
wording.
