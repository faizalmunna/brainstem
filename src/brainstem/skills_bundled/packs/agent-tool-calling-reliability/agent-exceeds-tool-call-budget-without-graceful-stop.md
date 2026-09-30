---
name: agent-exceeds-tool-call-budget-without-graceful-stop
description: An agent keeps issuing tool calls past a reasonable step or cost budget and is killed abruptly instead of wrapping up gracefully with partial results.
triggers: ["agent ran too many steps", "cost runaway from agent tool calls", "agent hit max iterations and just stopped", "no graceful shutdown for long agent run", "token budget exceeded mid-task"]
permissions: ["READ"]
---

## Symptom
A hard step-count or token/cost limit kills the agent loop mid-task with
no warning to the model and no attempt to summarize what was
accomplished -- the user gets either a truncated, useless partial
response or nothing at all, even though the agent may have been close to
done or could have produced a useful partial answer if it had known the
budget was about to run out.

## Likely causes
1. **The budget limit is enforced as a hard external cutoff** (a loop
   counter, a timeout, a token-count check) that terminates the process
   the instant it's exceeded, with no mechanism to warn the model
   beforehand that it's approaching the limit.
2. **The task naturally has unbounded scope for how the model chooses to
   pursue it** (e.g. "research this thoroughly") and nothing in the
   prompt or budget design gives the model an incentive or a way to
   scope its own work to fit within the budget.
3. **No distinction between "budget exhausted because of a loop/
   inefficiency"** (see the repeated-tool-call-loop skill in this pack)
   **and "budget exhausted because the task legitimately needs more
   steps than allotted"** -- the harness treats every over-budget case
   identically instead of adapting the response.
4. **The agent has no explicit "finalize and report" action** distinct
   from its normal tool calls, so even if it somehow realized it was
   near the limit, it has no clean way to stop early and summarize.

## Diagnose
- Check how the current budget enforcement actually terminates the
  loop -- does it throw/kill immediately at the limit, or does anything
  fire before that point?
- Look at a sample of runs that hit the budget limit and check whether
  they show signs of an inefficiency (repeated calls, no progress) versus
  genuine legitimate task complexity that simply needed more steps --
  these need different fixes (loop detection versus budget/scoping
  changes).
- Measure how often runs finish comfortably under budget versus how
  often they hit the ceiling -- a limit hit on a large fraction of runs
  suggests the budget itself is miscalibrated for the task, not that
  every one of those runs is broken.
- Check whether any partial results/intermediate findings from the
  killed run were captured anywhere, or whether hitting the limit means
  total loss of everything done in that run.

## Fix
Treat the budget as a soft warning threshold before it becomes a hard
stop. When usage crosses a configurable fraction of the limit (e.g. 80%),
inject a message into the agent's context stating explicitly that the
budget is almost exhausted and instructing it to wrap up: summarize
progress, state what remains undone, and produce the best available
answer with current information rather than continuing to explore. Give
the agent an explicit "finalize" step as part of its normal action set
so this isn't a special, untested code path. Only after that grace
window elapses (the model ignores the warning or the absolute hard limit
is reached) does the harness force-terminate, and even then it should
capture and return whatever partial output/reasoning existed rather than
discarding it. Separately, calibrate the budget itself based on
observed step-count distributions for legitimate task completions, and
apply the loop-detection pattern (see this pack) to distinguish "needs
more budget" from "spinning uselessly" so the two aren't solved by
simply raising the ceiling.

## Pitfalls
- Raising the budget ceiling as a blanket fix for hitting limits without
  checking whether the runs hitting it were actually looping
  unproductively -- this just delays the same failure and burns more
  cost per occurrence.
- Sending the "budget almost exhausted" warning too late to be useful
  (e.g. at 99% used) -- leave enough headroom after the warning for the
  model to actually execute a wrap-up turn, which itself costs some of
  the remaining budget.
- Building the graceful-stop path as a one-off special case that's never
  exercised in normal testing -- test it explicitly by forcing a run to
  hit the threshold, since untested error/edge paths in agent harnesses
  are exactly where crashes hide.

## Verify
Force a task to exceed the budget in a controlled test (set an
artificially low limit) and confirm the agent receives the warning
before the hard cutoff, produces an explicit summary of partial progress
and remaining work in response to it, and the harness returns that
summary to the caller instead of an empty or hard-failed response when
the limit is finally enforced.
