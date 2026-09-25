---
name: report-lists-findings-without-business-risk-context
description: A penetration test report lists technical findings with generic severity ratings but no explanation of actual business impact, making it hard for stakeholders to prioritize remediation.
triggers: ["pentest report no business context", "findings not prioritized by real risk", "generic severity rating not actionable", "report technical but not useful for prioritization"]
permissions: ["READ"]
---

## Symptom

A penetration test report delivers a list of technical findings each
tagged with a generic severity level (critical/high/medium/low, often
from a standardized scoring system), but non-technical stakeholders
(management, product owners) can't tell from the report which findings
actually threaten something the business cares about versus which are
theoretically severe but practically low-impact for this specific
system, making remediation prioritization difficult.

## Likely causes

- **The report was written primarily for a technical audience**
  (security engineers) using standardized vulnerability scoring (CVSS or
  similar) without translating that into what it actually means for the
  specific business -- "this could lead to remote code execution" without
  connecting it to "which means an attacker could access customer
  payment data."
- **The severity scoring system used is generic and context-free by
  design** (CVSS scores a vulnerability's inherent characteristics, not
  its actual exploitability or impact in this specific deployment
  context), so a technically-severe finding on an isolated, low-value
  system scores the same as an equally severe finding on a
  customer-data-holding system.
- **The tester didn't have (or didn't seek) enough business context about
  what data/functionality each tested system actually handles**, making
  it hard for them to translate technical severity into business risk
  even if they wanted to.
- **The report template used doesn't have a dedicated section connecting
  findings to business impact**, so even a tester with the right context
  might not include it if the reporting format doesn't prompt for it.

## Diagnose

1. Review the report structure for whether it includes any explicit
   business-impact narrative per finding, or only technical severity
   scores and technical descriptions.
2. For the highest-severity findings, check whether the report explains
   what specific business asset/capability is actually at risk (customer
   data, financial transactions, service availability) or leaves that
   inference to the reader.
3. Interview the stakeholders who received the report about which
   findings they actually understood the real-world impact of versus
   which they couldn't prioritize from the report alone.
4. Check whether the tester had access to business context (what
   systems handle what data) during the engagement, or was working
   purely from a technical scope document.

## Fix

Require (in the engagement scope/reporting template) that each finding
above a certain severity threshold include an explicit business-impact
statement, translating the technical vulnerability into concrete terms
(what data could be exposed, what functionality could be disrupted, what
compliance requirement could be violated) specific to this
organization's actual systems. Provide testers with relevant business
context (what each in-scope system does, what data it handles) as part
of scoping the engagement, so they can write meaningfully contextualized
findings rather than purely technical ones. Consider a supplementary
executive summary that ranks findings by business risk specifically,
separate from (but referencing) the detailed technical findings.

## Pitfalls

Don't let business-impact framing become vague or exaggerated to make
findings sound more urgent than they are -- overstating impact to drive
prioritization erodes trust in the report over time; keep the
business-impact narrative as accurate and specific as the technical
finding itself.

## Verify

For the next engagement, confirm the delivered report includes explicit
business-impact statements for high-severity findings, and confirm with
stakeholders (via a follow-up conversation) that they can now correctly
prioritize remediation based on the report alone, without needing
additional technical translation from the security team.
