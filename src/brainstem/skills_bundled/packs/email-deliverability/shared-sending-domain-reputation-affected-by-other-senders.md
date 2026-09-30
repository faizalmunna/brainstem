---
name: shared-sending-domain-reputation-affected-by-other-senders
description: Email deliverability degrades because a shared sending domain or IP pool used by a third-party email service is also used by other, lower-quality senders whose behavior damages the shared reputation.
triggers: ["shared ip pool deliverability problem", "email provider shared domain reputation", "other sender hurt deliverability", "third party email service reputation issue"]
permissions: ["READ"]
---

## Symptom

An application's email deliverability degrades noticeably without any
corresponding change in its own sending practices, content, or volume --
investigation reveals the email sending service uses a shared IP pool or
shared sending domain also used by other customers, and one or more of
those other senders' poor practices (spam complaints, high bounce rates)
damaged the shared reputation that this application's emails are riding
on.

## Likely causes

- **The email sending provider's default/lower-tier plan uses a shared IP
  pool across many customers**, meaning the sending reputation is a
  collective one -- any customer sharing the pool with genuinely poor
  sending practices can degrade deliverability for every other customer
  on the same pool.
- **No dedicated sending domain/IP was configured**, so the application's
  emails are sent using the provider's own shared domain rather than a
  domain the application controls and is solely responsible for the
  reputation of.
- **The provider doesn't proactively communicate or isolate problematic
  senders quickly enough** to prevent shared-pool damage from
  accumulating before it's addressed, leaving affected customers to
  discover the impact only through their own degraded deliverability
  metrics.
- **Cost considerations kept the application on a shared-pool tier**
  without weighing the deliverability risk against the cost savings,
  since the tradeoff wasn't well understood until it actually caused a
  problem.

## Diagnose

1. Check the specific plan/tier of the email sending provider in use and
   confirm whether it uses a shared or dedicated IP/domain.
2. Check the provider's own reputation/deliverability dashboards (many
   offer visibility into shared pool health) for signals of degraded
   shared reputation.
3. Compare deliverability trends against the application's own sending
   volume/content/practice changes to confirm the degradation isn't
   actually self-caused, ruling out other explanations first.
4. Contact the provider's support for visibility into whether a shared
   pool issue is known/being addressed on their side.

## Fix

Migrate to a dedicated sending IP and/or dedicated sending domain
(most established email providers offer this as a paid tier), so
sending reputation is solely determined by this application's own
practices rather than being shared with other customers. If staying on a
shared pool for cost reasons, choose a provider with a good track record
of actively monitoring and quickly isolating problematic senders on
their shared infrastructure, and monitor deliverability closely enough
to catch shared-pool degradation early.

## Pitfalls

Don't migrate to a dedicated IP without also properly warming it up (a
gradual increase in sending volume over the initial weeks) -- a
dedicated IP starts with no reputation at all, and sending high volume
immediately on a brand-new dedicated IP can trigger spam filtering just
as badly as a damaged shared reputation would, defeating the purpose of
the migration.

## Verify

After migrating to (and properly warming) a dedicated sending
IP/domain, monitor deliverability metrics (inbox placement, bounce rate,
complaint rate) over subsequent weeks and confirm they're now stable and
determined solely by this application's own sending behavior, with no
further unexplained degradation traceable to other senders.
