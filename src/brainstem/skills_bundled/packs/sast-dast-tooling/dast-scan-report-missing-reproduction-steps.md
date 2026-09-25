---
name: dast-scan-report-missing-reproduction-steps
description: Developers can't reproduce a DAST finding from the scan report alone and bounce it back untriaged because the request context is missing.
triggers: ["cant reproduce this zap finding", "dast report doesnt have enough info", "developer bounced back the dast ticket", "burp finding has no repro steps", "security ticket lacks curl command"]
permissions: ["READ"]
---

## Symptom
A DAST scan produces a finding (reflected XSS, SQL injection indicator,
missing security header) and the auto-generated ticket handed to a
developer contains only the vulnerability class name and the affected
URL, with no request method, headers, body, cookies/session state, or
the exact payload that triggered it. The developer can't reproduce the
issue in a browser or a REST client, marks it "can't reproduce" or "needs
more info," and it bounces back to security -- repeating for every
finding of this type and creating friction that makes developers
distrust DAST tickets specifically (as opposed to distrusting DAST
findings' validity, which is a different, false-positive-driven
problem).

## Likely causes
1. **The ticket-creation integration only forwards a summary field**
   (finding name + URL) from the scanner's API/webhook rather than the
   full request/response pair the scanner itself captured, because the
   integration was built against a minimal subset of the tool's export
   format.
2. **The vulnerable request depended on scan-session-specific state**
   (a CSRF token, a session cookie, a multi-step sequence like "add item
   to cart, then submit this parameter") that isn't captured by a
   single static URL, so even a full single-request replay fails without
   the surrounding sequence.
3. **The finding was on a POST/PUT request with a body payload**, and
   the ticket template was written assuming GET-style findings (URL
   with query string is self-contained), so body-based findings lose
   the actual attack payload in translation.
4. **The report was generated well after the scan ran** against an
   environment that has since changed (staging redeployed, test data
   reset), so even a technically complete repro no longer reproduces
   because the underlying state moved on.

## Diagnose
- Open the original finding directly in the scanner's own UI/report
  (not the downstream ticket) and check whether it includes a full
  request/response capture (method, headers, cookies, body) -- almost
  all DAST tools retain this internally even when the ticket integration
  doesn't forward it, confirming the gap is in the export/integration
  step, not the scan itself.
- Check the ticket template/integration config (a webhook payload
  mapping, a Jira plugin field mapping) for which fields it actually
  pulls from the scanner's finding object versus what's available in the
  scanner's full schema.
- Attempt to replay the request exactly as captured in the scanner's own
  UI (via "Copy as curl," "Send to Repeater," or equivalent) against the
  current environment to distinguish "ticket is missing info" from
  "environment state has changed since the scan," which need different
  fixes.
- Check whether the finding required a multi-step sequence (visible in
  the scanner's site-map/history around the finding) versus being a
  single self-contained request.

## Fix
Update the ticket-generation integration to include the full captured
request (method, URL, headers, cookies, body) and, where the scanner
supports it, an auto-generated curl/HTTPie command or exported
Postman/Insomnia collection entry that reproduces the exact request --
most mainstream DAST tools (ZAP, Burp) can export this directly, so the
fix is usually in the integration/template layer rather than needing new
scan capability. For findings that depend on session/multi-step state,
include the preceding steps in the ticket (either as a short sequence
description or a saved session/macro reference) rather than only the
final triggering request. Timestamp the report and, where the
environment is volatile, note the environment/build version the finding
was captured against so a developer can tell whether "can't reproduce"
means "ticket is incomplete" or "the target has since changed."

## Pitfalls
- Dumping the scanner's entire raw HTTP transaction log into the ticket
  without curating it (extracting just the reproducing request) shifts
  the burden of finding the signal back onto the developer, which
  produces the same bounce-back behavior for a different reason (too
  much noise instead of too little information).
- Auto-generated curl commands that don't include the session
  cookie/auth token (often deliberately stripped for security in
  ticket-management tools) look complete but silently fail to
  reproduce authenticated findings -- flag clearly when auth material
  was intentionally redacted and how to supply it locally, rather than
  leaving the ticket looking self-sufficient when it isn't.
- Treating "developer says can't reproduce" as automatically a false
  positive and closing the ticket skips the step of checking whether the
  repro info was simply incomplete -- verify reproducibility from the
  scanner's own capture before accepting either conclusion.

## Verify
Pick a recently bounced-back ticket, apply the improved template/export
to regenerate it with full request capture, and have a developer who
was not involved in the original scan attempt to reproduce the finding
using only the ticket's contents -- successful reproduction without
consulting the scanner's own UI confirms the ticket is now
self-sufficient.
