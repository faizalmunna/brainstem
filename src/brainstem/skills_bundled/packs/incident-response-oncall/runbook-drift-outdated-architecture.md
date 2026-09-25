---
name: runbook-drift-outdated-architecture
description: A runbook for a specific alert is out of date relative to the current system architecture and actively misleads whoever follows it during a real incident.
triggers: ["runbook is out of date", "runbook told me to do the wrong thing", "runbook references a service that no longer exists", "followed the runbook and it made things worse", "stale runbook during incident"]
permissions: ["READ"]
---

## Symptom
During a live incident, an on-call engineer opens the linked runbook for
the firing alert and follows its steps -- restart a specific service,
check a specific queue, run a specific command -- only to find the
service was renamed or decomposed months ago, the command references
infrastructure that's been migrated away from, or the described
remediation no longer applies to how the system currently behaves.
Precious incident time is spent realizing the runbook is wrong and
improvising instead of following it, or worse, the described action is
taken anyway and doesn't help (or actively makes things worse) because
it targeted the old architecture.

## Likely causes
- **The runbook was written once, during or after the incident/alert's
  original creation, and never revisited** even as the underlying system
  was refactored, renamed, split into microservices, or moved to new
  infrastructure.
- **No ownership is attached to the runbook** -- it isn't anyone's
  responsibility to update it when they change the system it describes,
  so architecture changes ship without a corresponding runbook update as
  a matter of routine, not exception.
- **The runbook lives disconnected from the code/infra it describes** (a
  wiki page with no link back to the service repo or IaC), so engineers
  changing the system have no prompt reminding them the runbook exists at
  all.
- **Runbooks are validated only by reading, never by execution** -- no
  one actually re-runs the steps against the current system (e.g. during
  a game day) to confirm they still work, so drift accumulates silently
  until a real incident exposes it.

## Diagnose
1. For the runbook in question, check its last-modified date against the
   service's last significant architecture change (a deploy history, an
   ADR, a migration ticket) -- a large gap is the direct signal.
2. Walk through the runbook's steps against the *current* system: does
   the named service/host/queue/dashboard still exist under that name? Do
   the commands reference current infrastructure (current cluster names,
   current tool versions)?
3. Check who owns the runbook -- is there a named team/individual, or is
   it orphaned wiki content with no clear owner to notice it's stale?
4. Ask whether the runbook has ever been executed end-to-end outside a
   real incident (a game day, a chaos exercise) -- if the only times it's
   been "tested" are live incidents, staleness is discovered at the worst
   possible time.

## Fix
Tie each runbook's freshness to the system it describes rather than
treating it as a standalone document: store it next to the
service's code/IaC (or link it prominently from both directions) so
changing the architecture makes the runbook visible in the same review,
and add a lightweight owner (the service's on-call team) responsible for
updating it as part of any change that would invalidate its steps.
Schedule periodic runbook validation independent of real incidents --
during a game day or scheduled chaos exercise, have someone unfamiliar
with recent changes actually execute the runbook's steps against the
current system and flag anything that doesn't match. Add a visible
last-verified date and owner directly on the runbook so a responder
mid-incident can immediately judge how much to trust it, rather than
discovering staleness by following bad instructions.

## Pitfalls
Don't treat "we updated the runbook" as done when only the prose was
edited without actually re-running the steps -- a runbook can look
current and still be wrong if no one executed it. Also avoid writing
runbooks so tightly coupled to exact transient details (specific pod
names, specific IPs) that they go stale on the next routine deploy --
write steps against stable interfaces (service names, dashboards, alert
names) where possible so ordinary operational churn doesn't require a
runbook edit every time.

## Verify
During the next scheduled game day or chaos exercise, have an engineer
who did not write the runbook execute it against production or a
faithful staging replica and confirm every referenced service, command,
and dashboard resolves correctly with no substitution or guessing
required. Also check that the runbook's last-verified date is within the
team's defined staleness window (e.g. reverified within the last two
quarters, or after any architecture change to the described system).
