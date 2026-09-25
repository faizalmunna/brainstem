---
name: data-residency-requirement-violated-by-default-region
description: A customer's data is stored or processed in a cloud region that violates their contractually or legally required data residency, because the application defaulted to a single global region.
triggers: ["data residency violation", "customer data in wrong region", "gdpr data transfer requirement violated", "data stored outside required jurisdiction"]
permissions: ["READ"]
---

## Symptom

A customer (or a compliance review) discovers that their data is being
stored or processed in a cloud region outside what their contract or
applicable law (a GDPR data-transfer restriction, a specific country's
data localization law) requires -- the application defaults to a single
global region/deployment rather than routing data based on customer
location or contractual requirement.

## Likely causes

- **The application was originally built as a single-region deployment**
  before data residency became a requirement for any customer, and
  region-awareness was never retrofitted as the customer base expanded
  to include jurisdictions with residency requirements.
- **A customer's data residency requirement was agreed contractually
  (during sales) without engineering being informed or the technical
  capability to honor it actually existing**, creating a commitment the
  system can't technically fulfill.
- **A specific data flow (backups, logs, a specific microservice, a
  third-party integration) processes data outside the primary
  region even though the main application data store is correctly
  region-scoped**, so residency is honored for the obvious primary case
  but violated by a less-visible secondary flow.
- **No automated check exists to verify actual data location matches
  required residency** on an ongoing basis, so a violation (from a
  misconfiguration, a new integration, an infrastructure change) isn't
  caught until an external review finds it.

## Diagnose

1. For the specific customer/data in question, trace exactly where their
   data is actually stored and processed -- primary database, backups,
   logs, caches, any third-party integrations -- not just the main
   application data store.
2. Compare each location against the actual contractual/legal residency
   requirement to identify precisely which flow(s) violate it.
3. Check whether the sales/contract process has any mechanism to verify
   a residency commitment is technically achievable before it's promised
   to a customer.
4. Check whether any automated monitoring exists for data location
   compliance, or whether this was discovered manually/externally.

## Fix

Implement region-aware data storage and processing for any component
that handles data subject to a residency requirement, ensuring the
customer's data (and all its derived copies -- backups, logs, replicated
analytics) stays within the required jurisdiction. Establish a process
requiring engineering/technical validation before a data residency
commitment is made contractually, so sales commitments are only made for
what's actually technically achievable (or trigger a scoped engineering
effort to make it achievable before commitment). Build automated,
ongoing verification of actual data location against required residency,
so a future violation (from misconfiguration or a new data flow) is
caught proactively rather than by an external party.

## Pitfalls

Don't treat data residency as satisfied just because the primary
database is correctly scoped -- backups, logs, caches, and third-party
integrations are common places residency violations hide even when the
"obvious" data store is compliant; audit the full data flow, not just
the most visible piece.

## Verify

Confirm the specific customer's data flow, including all derived copies,
now stays entirely within the required region/jurisdiction. Set up
ongoing automated monitoring for data location and confirm it correctly
flags a deliberately introduced test violation (a resource created in
the wrong region) before considering the fix complete.
