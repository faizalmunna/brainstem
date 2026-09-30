---
name: dmarc-policy-blocks-legitimate-forwarded-mail
description: A strict DMARC reject/quarantine policy causes legitimate emails to fail delivery when recipients forward mail or use mailing lists that break DKIM/SPF alignment.
triggers: ["dmarc rejecting forwarded mail", "mailing list breaks dmarc", "dmarc quarantine legitimate email", "spf fails after forwarding"]
permissions: ["READ"]
---

## Symptom

Emails sent from a domain with a strict DMARC policy (`p=reject` or
`p=quarantine`) are rejected or quarantined by receiving servers in
specific scenarios -- notably when a recipient's mail is forwarded by
another server, or when the message passes through a mailing list --
even though the original send was fully legitimate and authorized.

## Likely causes

- **Mail forwarding breaks SPF alignment** because the forwarding server
  becomes the new sending IP, which isn't included in the original
  domain's SPF record, causing SPF to fail on the final hop even though
  the original send passed.
- **Mailing lists or forwarding services modify message content**
  (adding a footer, altering the subject line) which breaks the DKIM
  signature, since DKIM signs the exact original content and any
  modification invalidates it.
- **DMARC policy is set to strict enforcement (`p=reject`) without ARC
  (Authenticated Received Chain) support**, which exists specifically to
  preserve authentication results across forwarding hops, but isn't
  configured or isn't honored by the receiving/forwarding servers
  involved.
- **DMARC alignment mode is set to strict rather than relaxed** for SPF
  or DKIM, requiring an exact domain match rather than allowing a
  subdomain match, which fails in common forwarding/subdomain sending
  setups that would otherwise pass under relaxed alignment.

## Diagnose

1. Reproduce the failure by forwarding a test email through the specific
   path being used (a mailing list, a personal forwarding rule) and
   inspect the resulting DMARC authentication results in the final
   delivered headers.
2. Check whether SPF, DKIM, or both failed on the forwarded hop, and
   whether at least one still passed (DMARC only requires one aligned
   pass).
3. Check current DMARC policy strictness (`p=reject` vs `p=quarantine`
   vs `p=none`) and alignment mode (`aspf`/`adkim` strict vs relaxed).
4. Check whether the forwarding/mailing-list path supports ARC and
   whether the receiving server honors ARC-sealed authentication results.

## Fix

Ensure DKIM signing covers only content that won't be modified by
common forwarding paths, so DKIM has the best chance of surviving
forwarding intact even when SPF doesn't. Use relaxed alignment mode for
SPF and DKIM unless there's a specific reason requiring strict
alignment, since relaxed mode tolerates common legitimate subdomain
variations. Roll out DMARC policy strictness gradually (`p=none` for
monitoring, then `p=quarantine`, then `p=reject`) using DMARC aggregate
reports to identify and fix legitimate-sender alignment issues before
tightening enforcement, rather than jumping straight to `p=reject` and
discovering forwarding breakage after the fact.

## Pitfalls

Don't disable DMARC enforcement entirely as a workaround for forwarding
breakage -- that discards the anti-spoofing protection DMARC exists to
provide; instead use the gradual rollout with aggregate report
monitoring to find the actual gap and address it specifically (ARC
support, alignment mode, DKIM signing scope) rather than abandoning
enforcement.

## Verify

Send test emails through each known forwarding/mailing-list path used by
real recipients and confirm they're delivered successfully with DMARC
passing (via SPF, DKIM, or ARC-preserved authentication) in the final
headers. Monitor DMARC aggregate reports after any policy change to
confirm legitimate sending sources continue passing alignment.
