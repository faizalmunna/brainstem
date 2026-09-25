---
name: vendor-subprocessor-not-covered-by-dpa
description: A third-party vendor that processes customer personal data on the company's behalf was never added to the required Data Processing Agreement or subprocessor list, creating a compliance gap.
triggers: ["vendor missing from dpa", "subprocessor not disclosed", "third party data processor no agreement", "vendor not on subprocessor list"]
permissions: ["READ"]
---

## Symptom

A compliance review or customer due-diligence questionnaire reveals that
a third-party vendor with access to customer personal data (an email
delivery service, an analytics provider, a support-ticketing tool) was
never formally added to the company's Data Processing Agreement (DPA)
coverage or its published subprocessor list, meaning data was shared
with them without the contractual and disclosure obligations GDPR (and
customer contracts referencing it) actually require.

## Likely causes

- **A new vendor/tool was adopted by an individual team** (engineering
  integrating a new analytics SDK, support adopting a new ticketing
  platform) without going through a procurement or legal review process
  that would have flagged the need for a DPA and subprocessor
  disclosure.
- **No inventory exists of which third-party services actually receive or
  process personal data**, so there's no systematic way to check new
  tool adoption against compliance requirements -- the gap is only
  discovered reactively, during an audit or a customer's own review.
- **A vendor was originally adopted for a purpose that didn't involve
  personal data, but its usage expanded over time** to include personal
  data processing without anyone revisiting its compliance coverage
  based on the new usage.
- **The subprocessor list/DPA process exists but isn't actually
  integrated into the tool-adoption workflow**, so even engineers aware
  of the requirement have no natural trigger point reminding them to
  follow it when adding a new vendor.

## Diagnose

1. Inventory all third-party services/vendors currently receiving or
   processing personal data, by reviewing actual data flows (API
   integrations, data exports, embedded SDKs) rather than relying only on
   a procurement record.
2. Cross-reference that inventory against the current published
   subprocessor list and existing DPAs to identify any vendor present in
   actual data flows but missing from formal coverage.
3. For each gap found, determine when the vendor started actually
   receiving personal data, to understand the duration of the compliance
   gap.
4. Review the current tool-adoption process (if any) for whether it
   includes a compliance/legal review checkpoint, and why it didn't
   catch this specific vendor.

## Fix

Execute a DPA with the identified vendor(s) and add them to the
published subprocessor list, bringing the actual data-sharing
relationship into formal compliance coverage. Build (or strengthen) a
tool-adoption process that requires a compliance/legal review checkpoint
before any new vendor is given access to personal data, rather than
relying on individual teams to remember the requirement. Maintain the
personal-data-flow inventory as a living document, reviewed periodically
(not just built once), so vendor usage expansion over time is caught
before it becomes a compliance gap rather than after.

## Pitfalls

Don't treat this as solved once the specific discovered vendor is
covered -- the same root cause (no systematic checkpoint) will produce
the same gap with the next new vendor unless the adoption process itself
is fixed, not just this one instance patched.

## Verify

Confirm the DPA is executed and the vendor appears correctly in the
published subprocessor list. Test the new tool-adoption process with a
hypothetical new vendor scenario and confirm the compliance/legal review
checkpoint actually triggers before data sharing would begin, not after.
