---
name: transactional-and-marketing-mail-share-reputation
description: Critical transactional emails like password resets fail to deliver because they share sending infrastructure and reputation with bulk marketing email that triggered spam filtering.
triggers: ["password reset email not delivered", "transactional email blocked by marketing spam", "critical email delayed same ip as newsletter", "separate transactional and marketing sending"]
permissions: ["READ"]
---

## Symptom

Critical, time-sensitive transactional emails (password resets,
order confirmations, two-factor authentication codes) fail to deliver
or are significantly delayed, and investigation reveals these emails
share the same sending domain, IP, or infrastructure as bulk marketing
email -- so a reputation hit from marketing sends (high complaint rate,
aggressive send volume) degrades deliverability for the unrelated,
higher-stakes transactional traffic riding on the same infrastructure.

## Likely causes

- **No separation exists between transactional and marketing sending
  infrastructure** -- both use the same sending domain/IP by default,
  either because the application was never architected with this
  distinction or because a single email provider account handles both
  without configuring separate sending identities.
- **Marketing email practices (list quality, send frequency, content)
  are inherently higher-risk than transactional email** (lower
  complaint tolerance, more aggressive volume, less strict opt-in
  discipline), so pooling them with transactional mail imports that risk
  onto traffic that shouldn't carry it.
- **The email provider's reputation/rate-limiting systems apply
  uniformly per sending identity**, so a marketing-driven reputation
  problem or rate-limit trigger throttles or blocklists transactional
  mail indiscriminately, even though the transactional mail itself
  followed good practices.
- **No monitoring distinguishes transactional deliverability from
  marketing deliverability**, so a marketing-caused reputation problem
  isn't caught until it's already visibly impacting critical
  transactional flows like password resets.

## Diagnose

1. Check the current sending configuration and confirm whether
   transactional and marketing email use the same or different sending
   domains/IPs/provider identities.
2. Review recent deliverability incidents and determine whether they
   correlate with marketing send events (a campaign, a large batch) even
   when the symptom appeared on transactional mail.
3. Check the email provider's plan/configuration for whether separate
   sending identities (subdomains, dedicated IPs) are available and
   whether they're actually being used.
4. Confirm complaint and bounce rate trends separately for what can be
   identified as marketing versus transactional traffic.

## Fix

Separate transactional and marketing email onto distinct sending
subdomains (e.g., `transactional.example.com` vs `marketing.example.com`)
with independent SPF/DKIM/DMARC configuration and, where the provider
supports it, independent reputation tracking -- so a marketing-caused
reputation issue can't directly degrade transactional deliverability.
Apply stricter sending discipline specifically to marketing mail (list
hygiene, opt-in verification, complaint-rate monitoring, gradual volume
ramping) since it's the higher-risk category, while transactional mail's
lower-risk, lower-volume, high-engagement profile builds and maintains
its own strong reputation independently.

## Pitfalls

Don't just use a different "From" display name or subject-line pattern
while still sending both mail types from the same underlying domain and
IP -- receiving mail providers evaluate reputation based on
authenticated sending domain and IP, not display name, so surface-level
separation without actual infrastructure separation doesn't isolate the
reputations.

## Verify

After separating sending domains, confirm each has independent
SPF/DKIM/DMARC passing and monitor each subdomain's reputation and
deliverability metrics independently. Simulate or observe a
marketing-mail reputation event and confirm transactional deliverability
(password resets, confirmations) remains unaffected on the separated
infrastructure.
