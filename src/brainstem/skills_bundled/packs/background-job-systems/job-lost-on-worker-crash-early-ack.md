---
name: job-lost-on-worker-crash-early-ack
description: A job vanishes with no failure or retry record because the worker acknowledged the message before finishing and then crashed mid-execution.
triggers: ["job disappeared without failing", "task lost after worker OOM", "message acked before job finished", "celery acks_late misconfigured", "job never completed and never retried"]
permissions: ["READ"]
---

## Symptom
A job simply vanishes: it was enqueued, a worker picked it up, and it never completed and never shows up as failed or retried anywhere -- traced to the worker process crashing (an OOM kill, a deploy, an uncaught native crash) after the message was already acknowledged but before the work actually finished.

## Likely causes
1. **The consumer acknowledges the message immediately on receipt rather than after successful completion** (an early/at-most-once ack configuration -- e.g. Celery with `task_acks_late` disabled, a manual ack call placed right after dequeue instead of after the task body finishes), so the broker considers the job done the instant a worker picks it up, regardless of whether it actually finishes.
2. **A deploy or scale-down event terminates worker processes without waiting for in-flight jobs to finish or without requeueing them**, and because the message was already acked, the broker has no record that the job needs to run again.
3. **A worker OOM kill (SIGKILL) during execution** loses the job even in a well-intentioned "ack after completion" design, since a hard kill can't be caught or handled by any application-level shutdown code.
4. **No dead-worker detection/requeue mechanism independent of ack timing is enabled**, even though the framework may support one -- a way to notice a worker that stopped heartbeating mid-job and put its in-flight work back on the queue.

## Diagnose
- Check the consumer's actual ack configuration: is the message acknowledged on receipt/dequeue, or only after the task function returns successfully (Celery `task_acks_late`, ack placement in a raw AMQP/SQS consumer, a queue library's default completion-triggers-lock-release behavior)?
- Reproduce deliberately in a non-prod environment: enqueue a job, SIGKILL the worker process partway through execution, and check whether the message reappears in the queue or is gone for good.
- Check deploy/autoscaling procedures for whether they send a graceful shutdown signal and wait for in-flight jobs to finish (a drain period) before terminating worker processes, or terminate immediately.
- Cross-reference enqueue logs against completion/failure logs for a sample time window to directly measure how many job ids have an enqueue record but neither a completion nor a failure record.

## Fix
Switch to late acknowledgment: acknowledge the message only after the job has fully completed, or has definitively failed in a way that's recorded, so a mid-execution crash leaves the message unacked and the broker redelivers it -- accepting the resulting at-least-once tradeoff (see the duplicate-delivery pattern for handling that safely) as preferable to silent loss. Configure graceful shutdown: catch SIGTERM to stop accepting new jobs and either wait for in-flight jobs to finish within a bounded drain period or explicitly requeue them, reserving SIGKILL for a hard timeout after that drain period rather than sending it first. Where the broker/framework supports it, enable worker-liveness-based requeue (a heartbeat mechanism where the broker or a supervisor notices a worker went silent mid-job and puts the message back) as a backstop for the OOM/SIGKILL case that no application-level signal handling can prevent. Explicitly decide the acknowledgment model per job type where some jobs genuinely tolerate at-most-once (a best-effort metrics ping where losing one is fine), rather than leaving late-ack-vs-early-ack as an unexamined framework default for jobs whose loss actually matters.

## Pitfalls
Switching to late-ack without also making the job idempotent just trades "jobs silently vanish" for "jobs silently duplicate" -- the two fixes belong together, not as alternatives. Relying solely on graceful shutdown handling doesn't cover OOM kills or host-level failures (spot instance reclamation, a node crash) that can't be gracefully signaled at all -- graceful shutdown shrinks the loss window, it doesn't replace late-ack/requeue as the actual safety net.

## Verify
Enqueue a job, SIGKILL the worker process mid-execution (not SIGTERM, to specifically exercise the hard-crash path) in staging, and confirm the message is redelivered and the job eventually completes -- safely, without duplicating its real-world side effect -- rather than disappearing with no record of failure or retry.
