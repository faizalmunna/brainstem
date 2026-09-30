---
name: emails-land-in-spam-despite-valid-content
description: Transactional or marketing emails consistently land in recipients' spam folders even though the content itself contains no obviously spammy language or links.
triggers: ["emails going to spam folder", "deliverability dropped suddenly", "transactional email marked as spam", "good content still flagged spam"]
permissions: ["READ"]
---

## Symptom

Emails sent from an application (password resets, order confirmations,
newsletters) are consistently delivered to recipients' spam/junk
folders rather than their inbox, despite the email content itself being
legitimate and free of obviously spam-triggering language, links, or
formatting.

## Likely causes

- **SPF, DKIM, or DMARC authentication records aren't correctly
  configured for the sending domain**, so receiving mail servers can't
  verify the email is genuinely authorized to be sent on behalf of that
  domain, a strong spam signal regardless of content quality.
- **The sending IP address or domain has a poor reputation** (from
  previous misuse by a prior owner of the IP, from high bounce/complaint
  rates on the current sending pattern, or from being on a public
  blocklist) that mail providers weight heavily regardless of individual
  message content.
- **Sending volume or pattern looks anomalous** to receiving mail
  providers' spam heuristics -- a sudden volume spike, sending to many
  invalid/non-existent addresses, or a pattern that resembles known spam
  campaign behavior even if the actual content is legitimate.
- **A specific receiving mail provider's spam filter has a false-
  positive rule triggered by something in the email's structure**
  (an unusual header, a mismatched "from" display name versus domain)
  that content alone wouldn't reveal without checking the raw headers.

## Diagnose

1. Verify SPF, DKIM, and DMARC records are correctly configured and
   actually passing by checking the raw headers of a delivered (even if
   spam-foldered) test email for authentication result headers.
2. Check the sending IP/domain's reputation using publicly available
   blocklist-checking tools and mail-provider-specific reputation/postmaster
   tools where available.
3. Review recent sending volume and bounce/complaint rate trends for any
   anomaly correlating with when deliverability dropped.
4. Send a test email to accounts across multiple major mail providers and
   compare inbox-vs-spam placement and any available spam-score/filter
   diagnostic feedback from each.

## Fix

Configure SPF, DKIM, and DMARC correctly and completely for the sending
domain, verified against actual delivered mail's headers, not just
configuration documentation. If sending reputation is the issue, work
through the specific mail provider's postmaster/reputation
rehabilitation process (often requiring a period of clean, low-complaint
sending volume) rather than expecting an immediate fix. Reduce bounce
and complaint rates by maintaining list hygiene (removing invalid
addresses, honoring unsubscribes promptly) and by ramping up sending
volume gradually for a new sending domain/IP rather than sending a large
volume immediately (IP/domain warming).

## Pitfalls

Don't respond to a deliverability problem purely by rewriting email
content to avoid "spam trigger words" -- modern spam filtering weighs
authentication, reputation, and engagement signals far more heavily than
specific words in content, and over-focusing on content wording while
ignoring authentication/reputation issues wastes effort on the less
impactful lever.

## Verify

After fixing authentication configuration, send test emails to accounts
across multiple major mail providers and confirm inbox placement
(not spam) alongside passing SPF/DKIM/DMARC checks in the delivered
headers. Monitor bounce/complaint rates and inbox placement rate over the
following weeks to confirm the improvement holds under real sending
volume, not just a single test.
