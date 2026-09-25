---
name: automated-scanner-output-mistaken-for-full-test
description: An automated vulnerability scanner's output is delivered and treated as a complete penetration test, missing business-logic and authorization flaws that automated tools structurally cannot detect.
triggers: ["scanner output labeled as pentest", "automated scan mistaken for penetration test", "no manual testing in pentest report", "business logic flaw missed by automated scan"]
permissions: ["READ"]
---

## Symptom

A "penetration test" deliverable turns out, on closer inspection, to be
largely or entirely the raw output of an automated vulnerability scanner
(re-formatted into a report) with little or no manual testing -- and a
real security incident later occurs exploiting a business-logic or
authorization flaw (a way to manipulate a price, bypass a workflow step,
access another user's data by guessing an ID) that automated scanning
tools are structurally unable to detect, since they don't understand
the application's intended business rules.

## Likely causes

- **A cost- or time-constrained engagement relied heavily on automated
  tooling to cover more ground quickly**, with manual testing time
  insufficient to actually probe business logic, which requires
  understanding what the application is supposed to do in order to find
  ways it can be made to do something it shouldn't.
- **The engagement was scoped/sold as a "penetration test" but was
  actually closer to a vulnerability scan**, either due to a
  misunderstanding between client and vendor about what was being
  purchased, or a vendor cutting corners on manual effort while still
  using penetration-testing terminology.
- **Automated scanners are good at finding known vulnerability
  signatures (outdated libraries, common injection patterns) but have no
  way to reason about business logic** (does this workflow allow a
  discount code to be applied twice, can a non-admin user reach an admin
  endpoint by guessing a URL) since that requires understanding intent,
  not just pattern-matching against known bad code.
- **No manual testing checklist/methodology (like OWASP's testing guide)
  was actually followed**, so there was no structured expectation that
  business-logic-focused manual testing categories would be covered.

## Diagnose

1. Review the report/deliverable for evidence of manual testing
   methodology versus purely automated scanner output -- check for
   custom test cases, business-logic-specific findings, or evidence the
   tester actually understood the application's specific workflows.
2. Compare the report's findings categories against a recognized manual
   testing methodology (like the OWASP Testing Guide) to identify which
   categories (typically business logic, authorization, workflow
   bypass) are conspicuously absent.
3. Check the original engagement scope/contract for what was actually
   promised (a full manual penetration test vs. an automated scan) versus
   what was delivered.
4. For the specific incident that occurred, confirm whether the
   exploited flaw was the kind of business-logic issue an automated
   scanner would have had no ability to detect.

## Fix

Explicitly scope future engagements to require manual testing time and
methodology coverage (not just automated scanning), with the contract
specifying expected manual testing categories (authorization/access
control testing, business logic testing, workflow abuse cases) rather
than leaving "penetration test" as an ambiguous term that could be
satisfied by automated scanning alone. Use automated scanning as a
component that feeds into and supports manual testing (covering known
vulnerability classes efficiently, freeing manual time for business
logic), not as a substitute for it. When selecting a testing vendor,
require evidence of manual testing methodology and deliverables from
past engagements before contracting.

## Pitfalls

Don't conclude automated scanning has no value and should be dropped
entirely -- it's genuinely efficient at covering known vulnerability
classes at scale, freeing manual testing time for what automation can't
do; the fix is ensuring both are actually present and clearly
distinguished in scope and reporting, not choosing one over the other.

## Verify

For the next engagement, review the contract/scope explicitly for manual
testing requirements before it begins, and confirm the delivered report
includes findings that could only have come from manual, business-
logic-aware testing (not just scanner signatures) as evidence the
methodology was actually followed.
