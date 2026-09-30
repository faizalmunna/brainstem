---
name: alert-fatigue-noisy-thresholds
description: On-call gets paged frequently for alerts that turn out to be non-actionable, and real incidents start getting missed or delayed because people stop trusting pages.
triggers: ["alert fatigue", "too many pages", "on-call is noisy", "getting paged for nothing", "alerts nobody acts on"]
permissions: ["READ"]
---

## Symptom

On-call engineers are paged multiple times a day/night for conditions
that resolve themselves, require no action, or are already known and
tolerated. Over time, response time to pages degrades and a real incident
gets missed or acknowledged late because it looked like "just another
noisy alert."

## Likely causes

- **Thresholds were set from a single observation** (a "looked bad once"
  value) rather than from the metric's actual normal variance, so routine
  fluctuation regularly crosses the line.
- **An alert fires on a symptom that self-heals** (a transient latency
  blip during a known traffic pattern, an autoscaler catching up) with no
  "for X minutes" duration requirement, so every brief blip pages someone.
- **Alerting on causes instead of user-facing symptoms** -- e.g. paging on
  "CPU > 80%" instead of "error rate > threshold" or "latency SLO
  breached" -- so infrastructure noise pages people even when users are
  unaffected.
- **Duplicate/overlapping alerts** from multiple monitoring systems (a
  cloud provider's built-in alerting plus a separately configured APM
  tool) fire for the same underlying issue, doubling page volume without
  doubling information.
- **An alert that was relevant during an incident was never removed or
  tuned down afterward**, so a one-time investigative alert became
  permanent noise.

## Diagnose

1. Pull the last 30-90 days of page history and group by alert
   name/rule -- a small number of rules almost always account for the
   majority of pages; find them before touching anything else.
2. For each high-volume alert, check the resolution: was there an action
   taken, or did it self-resolve/get acknowledged with no follow-up? A
   high self-resolve rate is the direct signature of a bad threshold or
   missing duration requirement.
3. Check whether the alert is cause-based or symptom-based -- if it's
   "CPU/memory/disk crossed X%," ask whether users were actually affected
   during those windows (cross-reference against error-rate/latency
   dashboards for the same period).
4. Check for duplicate coverage: does more than one alerting system fire
   for the same underlying condition?

## Fix

Rewrite noisy alerts to page on **user-facing symptoms** (SLO burn rate,
error rate, latency percentile breach) rather than resource-level causes,
and require a sustained duration (e.g. "5 minutes above threshold," not
"one data point above threshold") before paging, using the metric's own
historical variance to set the threshold rather than a single bad
observation. Route genuinely informational conditions (approaching a
quota, a resource trending toward a limit) to a non-paging channel
(dashboard, ticket, low-priority Slack notification) instead of a page.
Deduplicate overlapping alert sources so one incident produces one page,
not several. Every alert should have a documented, specific expected
action in its runbook link -- an alert with no plausible action attached
is a dashboard panel, not a page.

## Pitfalls

Don't fix alert fatigue by simply raising every threshold until pages
stop -- that trades false positives for false negatives and can hide a
real, slower-building incident until it's much worse. Also don't remove
an alert entirely just because it's currently noisy without first fixing
*why* it's noisy (duration, threshold, symptom vs. cause) -- the
underlying condition it was meant to catch is often still worth knowing
about, just not via an interrupt-driven page.

## Verify

Track page volume and the self-resolve/no-action rate for 2-4 weeks after
retuning; a successful fix shows materially fewer pages with a materially
higher fraction resulting in real action. Also confirm, via a
deliberately induced or historical replay of a real past incident, that
the retuned alert would still have fired in time to catch it -- tuning
noise down must not have also tuned out real signal.
