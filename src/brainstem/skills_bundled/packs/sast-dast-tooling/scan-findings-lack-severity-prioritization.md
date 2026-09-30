---
name: scan-findings-lack-severity-prioritization
description: Scan results queue every finding in raw discovery order so a low-risk issue sits ahead of a critical one with no exploitability-based triage.
triggers: ["security backlog is just a flat list", "critical finding sat untriaged for weeks", "we dont prioritize security findings by risk", "triage queue is first-in-first-out", "no way to tell which finding matters most"]
permissions: ["READ"]
---

## Symptom
SAST, DAST, and SCA findings all land in the same backlog (a Jira
project, a security dashboard, a spreadsheet) with no consistent
severity/exploitability-based ordering -- tickets get worked roughly in
creation-date order or by whoever happens to pick them up, so a
low-impact informational finding created last week gets addressed before
a critical, internet-reachable finding that's been sitting for a month,
purely because of queue position rather than actual risk.

## Likely causes
1. **Findings from different tools use incompatible severity scales**
   (a SAST tool's "high," a DAST tool's CVSS score, an SCA tool's
   vendor-assigned rating) and get dumped into one backlog with no
   normalization, so sorting "by severity" isn't even meaningful across
   the combined queue.
2. **Tool-assigned severity is treated as final** without adjusting for
   actual exploitability/context (internet-facing vs. internal-only
   service, presence of compensating controls, data sensitivity of the
   affected system), so two findings with the same tool-assigned
   "high" label can have wildly different real-world risk with no
   distinction made.
3. **No single triage queue exists at all** -- findings live scattered
   across each tool's own dashboard (the SAST vendor's UI, the DAST
   vendor's UI, GitHub security tab for SCA) with nobody responsible for
   pulling them into one prioritized view, so prioritization never
   happens because there's no single place to prioritize from.
4. **Ticket creation is fully automated with no triage gate before
   entering the team's normal sprint backlog**, so security findings
   compete for attention using the same "oldest first" or "whoever grabs
   it" norms as ordinary feature work, which isn't how risk-based work
   should be sequenced.

## Diagnose
- Pull the current open backlog of security findings across all tools
  and check whether each has any normalized severity/priority field
  populated versus only carrying the raw tool-specific label.
- Sample the oldest 10 open findings and the newest 10, and compare
  their actual severity/exploitability -- if there's no correlation
  between age and severity (old low-severity items sitting next to
  recently-closed critical ones), that confirms FIFO-by-default handling
  rather than risk-based triage.
- Check whether a documented triage rubric exists anywhere (a wiki page,
  a runbook) defining how severity + exploitability + exposure combine
  into a priority -- absence of any written rubric is itself diagnostic,
  since undocumented triage tends to default to whoever's loudest or
  first.
- Check whether findings carry any exposure/context metadata (is this
  service internet-facing, does it touch regulated data) -- if the only
  metadata is the raw tool output, there's no substrate for
  context-aware prioritization even if someone wanted to do it manually.

## Fix
Establish a single normalized triage rubric that combines each finding's
technical severity (normalize across tools into one scale, e.g. mapping
each tool's rating to CVSS-like Critical/High/Medium/Low) with
contextual exploitability factors -- is the affected component
internet-reachable, does it require authentication, does it touch
sensitive data, is there a compensating control already in place -- to
produce one priority score per finding regardless of source tool.
Funnel all findings (SAST, DAST, SCA) into one triage queue using this
rubric before they enter the team's normal work backlog, with an
explicit SLA per priority tier (e.g. critical triaged within 24 hours,
low within a sprint), so the queue is ordered by actual risk rather than
discovery order. Assign a rotating or dedicated triage owner responsible
for applying the rubric consistently, rather than leaving prioritization
to whoever picks up a ticket.

## Pitfalls
- Building an elaborate scoring rubric that takes longer to apply than
  just fixing simple findings defeats its own purpose -- keep the rubric
  to a small number of concrete factors (severity, reachability,
  exposure) rather than an exhaustive weighted formula nobody applies
  consistently under time pressure.
- Letting tool-assigned severity silently override the rubric when
  they disagree (treating a tool's "critical" label as automatically
  top-priority even when context clearly reduces real risk, e.g.
  internal-only tooling with no external exposure) reintroduces
  unadjusted-severity bias by another name.
- Prioritizing so aggressively on "critical only" that medium/low
  findings never get scheduled at all lets a slow accumulation of
  unaddressed medium-risk issues become a real problem later -- ensure
  lower tiers still have a non-zero, if slower, remediation cadence.

## Verify
Audit the triage queue after adopting the rubric and confirm findings
are actually ordered/labeled by the normalized priority rather than
creation date -- spot-check that the oldest few tickets in the "low"
tier are older than the newest "critical" tier ticket, confirming
severity, not age, now drives work order, and confirm each open finding
has the rubric's context fields (exposure, exploitability) populated
rather than blank.
