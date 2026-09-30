---
name: dkim-signature-invalidated-by-relay-modification
description: DKIM signature verification fails because an intermediate mail relay or gateway modifies email headers or body content after the message was signed.
triggers: ["dkim signature invalid after relay", "dkim fail gateway modifies email", "dkim verification broken in transit", "email security gateway breaks dkim"]
permissions: ["READ"]
---

## Symptom

DKIM verification fails on delivered emails even though the sending
system signed the message correctly at send time -- investigation shows
an intermediate mail relay, security gateway, or list-processing service
between the sender and recipient is modifying message headers or body
content in transit, invalidating the cryptographic signature that was
valid when the message left the origin server.

## Likely causes

- **A corporate email security gateway rewrites links or adds a warning
  banner** to inbound mail for phishing protection, which alters the
  signed body content and breaks the DKIM body hash even though the
  gateway isn't the final recipient.
- **The DKIM signature covers headers that a relay legitimately needs to
  modify** (like adding a `Received` header or modifying `Subject` for
  list identification), and the signing configuration didn't anticipate
  which headers would survive relay transit unmodified.
- **A mailing list or distribution service modifies the message** (adding
  list-unsubscribe footers, rewriting the "From" or "Reply-To") as part
  of its normal function, which is fundamentally incompatible with
  DKIM's assumption that the signed content stays exactly as sent.
- **The signing key's canonicalization mode is too strict** ("simple"
  rather than "relaxed"), making the signature fragile to even
  whitespace or minor formatting changes introduced by intermediate
  systems that a more tolerant canonicalization mode would survive.

## Diagnose

1. Capture the raw headers of a delivered message that failed DKIM
   verification and identify every `Received` hop between origin and
   final delivery.
2. Compare the DKIM-signed header list (`h=` tag in the DKIM-Signature
   header) against which headers/body actually changed between sending
   and final delivery.
3. Test whether the same message delivered via a path without the
   suspected intermediate (a direct send, bypassing the relay/gateway)
   passes DKIM verification, isolating the intermediate as the cause.
4. Check the DKIM signature's canonicalization mode (`c=` tag) for
   whether it's set to strict "simple" versus more tolerant "relaxed".

## Fix

Switch DKIM canonicalization to "relaxed" mode for both header and body
(if not already), which tolerates minor formatting changes without
breaking the signature. For content genuinely modified by a known
necessary intermediate (a corporate gateway, a mailing list), rely on
ARC (Authenticated Received Chain) to preserve the original
authentication result through that hop rather than expecting DKIM alone
to survive intentional content modification. Where possible, coordinate
with the operator of the modifying intermediate to exclude
DKIM-critical traffic from modification, or to re-sign the message with
their own DKIM key after modification so the final hop has its own valid
signature.

## Pitfalls

Don't assume a DKIM failure automatically means the message is spoofed
or fraudulent -- legitimate relay-caused signature breakage is common
enough that DKIM failure alone shouldn't trigger automatic rejection
without also checking SPF and, ideally, ARC-preserved results from
known-legitimate intermediate hops.

## Verify

After switching to relaxed canonicalization, send test messages through
the same intermediate path that previously broke DKIM and confirm the
signature now verifies successfully at final delivery. For paths with
unavoidable content modification, confirm ARC seals are present and
correctly preserve the original authentication result through the
delivery chain.
