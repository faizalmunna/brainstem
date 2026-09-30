---
name: multi-step-agent-task-no-checkpoint-resume
description: A long multi-step agentic task fails partway through and must restart entirely from scratch because there's no checkpoint or resume capability.
triggers: ["agent has to restart from scratch after failure", "no way to resume a failed agent run", "long task dies and loses all progress", "checkpoint agent progress", "resume interrupted agent task"]
permissions: ["READ"]
---

## Symptom
A task that involves many sequential tool calls (a migration across
hundreds of records, a multi-file refactor, a long research pipeline)
fails at, say, step 80 of 100 -- due to a transient tool error, a rate
limit, a crash, or a token/cost budget hit -- and the only recovery path
is re-running the entire task from the beginning, including the 79 steps
that already completed successfully and may even get redone with side
effects repeated.

## Likely causes
1. **The agent's state lives only in the in-memory conversation
   history/context for the current process** -- nothing about progress
   is persisted anywhere durable, so a process crash or restart loses
   everything accumulated in that context.
2. **Tool actions aren't idempotent**, so even if you could resume and
   re-issue the last few calls, doing so risks double-applying side
   effects (duplicate writes, duplicate emails) rather than safely
   continuing.
3. **No explicit notion of "task state" separate from "conversation
   history"** -- the system was built assuming the conversation itself
   is the source of truth, which works until it needs to survive a
   restart, be resumed by a different process, or be inspected/modified
   mid-flight.
4. **The task decomposition itself is monolithic** -- one long-running
   agent loop handles the entire multi-step task as a single continuous
   session instead of being modeled as discrete, individually-trackable
   sub-tasks with their own completion status.

## Diagnose
- Check what happens to task progress today on a mid-task crash: is
  there any persisted record (a database row, a file, a queue message)
  of which steps completed, or does progress exist only in an
  in-memory/ephemeral conversation object?
- Identify whether the tools the task relies on are idempotent (safe to
  call twice with the same effect) or not -- this determines whether
  naive replay-from-last-known-step is safe or dangerous.
- Estimate the cost (time, tokens, money, external side effects) of a
  full restart versus the frequency of partial failures in production --
  this quantifies whether checkpointing is worth the engineering cost
  for this specific task's failure rate and step count.
- Look at whether the task is currently modeled as one long agent
  session or as a sequence of separable units -- a task that's already
  naturally chunked (per-record, per-file) is much cheaper to add
  checkpointing to than one continuous freeform loop.

## Fix
Model the multi-step task as an explicit state machine with durable,
externally-visible progress, not as an opaque conversation. Persist a
checkpoint record after each completed unit of work (e.g. per record,
per file, per pipeline stage) to durable storage -- what's been
completed, what the next pending unit is, and any accumulated
intermediate results needed to continue -- independent of the agent
process's memory. On restart, resume by loading the last checkpoint and
continuing from the next pending unit rather than replaying everything.
Make each unit of work idempotent (checked via an idempotency key or a
pre-check like "does this record already have the target state") so
that even an ambiguous crash (did that last write commit or not) can
safely be retried without double-applying effects. Decompose large tasks
into the smallest sensible checkpointable units up front, since
checkpoint granularity directly determines how much work is lost on
failure.

## Pitfalls
- Adding checkpointing at too coarse a granularity (e.g. only at the very
  end of a 100-item batch) which technically satisfies "there's a
  checkpoint" but still loses 99 items of progress on a late failure --
  size checkpoint units to the actual cost of redoing one unit.
- Persisting the checkpoint state but not the reasoning/context the agent
  needs to correctly resume (e.g. why it skipped certain items, decisions
  made along the way) -- a resumed agent with only "step 80 done" and no
  context can make different, inconsistent decisions than a continuous
  run would have.
- Assuming idempotency for free by adding a checkpoint without actually
  auditing whether the underlying tool calls are safe to repeat --
  checkpointing without idempotent actions just changes where duplicate
  side effects happen, not whether they can happen.

## Verify
Kill the agent process partway through a realistic multi-step task
(e.g. at step 40 of 100, mid-unit) and confirm: on restart, it resumes
from the correct next unit without re-processing already-completed
units, no side effect (write, email, charge) is duplicated for the
in-flight unit at the time of the kill, and the final end-to-end result
matches what an uninterrupted run would have produced.
