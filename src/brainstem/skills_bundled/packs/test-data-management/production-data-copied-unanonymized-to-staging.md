---
name: production-data-copied-unanonymized-to-staging
description: Production data was copied into a staging or test environment without anonymization, exposing real customer information to anyone with access to the lower environment.
triggers: ["production data in staging unmasked", "pii exposed in test environment", "database copy not anonymized", "compliance issue test data"]
permissions: ["READ"]
---

## Symptom

A security review, compliance audit, or an engineer noticing something
they shouldn't be able to see reveals that a staging, QA, or development
database contains real, unmasked production customer data (real names,
emails, payment details, addresses) -- accessible to a much broader set
of people (all engineers, contractors, CI systems) than production data
access is normally restricted to.

## Likely causes

- **A database snapshot/dump/restore process copies production data
  directly into a lower environment** for realistic testing purposes,
  with no anonymization step ever added to that pipeline.
- **An anonymization step exists but doesn't cover every sensitive
  field** -- new columns/tables added over time (a new PII field on a
  profile, a new table storing payment metadata) were never added to the
  anonymization script's scope, so it silently misses newly introduced
  sensitive data.
- **Anonymization runs but is reversible or too weak** (a simple
  substitution cipher, predictable masking) that could be reverse-
  engineered, providing a false sense of compliance without a real
  security benefit.
- **A one-off manual copy was done for urgent debugging** ("just this
  once, to reproduce a customer's exact issue") and never cleaned up or
  brought under the same anonymization process as regular refreshes.

## Diagnose

1. Inventory every lower environment (staging, QA, dev, local
   developer databases, CI test databases) that has ever been populated
   from a production data source, and check each for an anonymization
   step in its provisioning process.
2. For an environment that does anonymize, review the anonymization
   script/config against the *current* production schema to find any
   sensitive columns/tables it doesn't cover -- specifically ones added
   after the anonymization script was last updated.
3. Sample actual data in the lower environment for recognizable real
   values (a known test account's real email, a real-looking payment
   card pattern) to confirm empirically whether anonymization is actually
   effective, not just present.
4. Check who/what has access to each lower environment and compare
   against the access controls applied to actual production data, to
   scope the real exposure.

## Fix

Build anonymization into the data-refresh pipeline itself as a mandatory,
automated step -- never a manual or optional one -- so every refresh from
production to a lower environment is anonymized by construction. Use
one-way, irreversible anonymization/masking (not simple reversible
substitution) for genuinely sensitive fields, and keep the anonymization
scope reviewed against schema changes (ideally enforced via a check that
flags new columns matching common PII patterns that aren't yet covered).
For urgent one-off debugging needs, provide a sanctioned, safe alternative
(a specific, access-controlled process to inspect a single real record
directly in production with proper audit logging) rather than allowing
ad hoc unanonymized copies as a workaround.

## Pitfalls

Don't treat anonymization as a one-time setup task -- schema evolves, and
an anonymization script that isn't kept in sync with schema changes will
silently regress exactly the way described above. Also don't assume
partial anonymization (masking obviously sensitive fields like email/SSN)
is sufficient without considering combinations of fields that could
re-identify someone even after individual fields are masked (a
combination of birthdate, zip code, and gender, for instance).

## Verify

After implementing pipeline-enforced anonymization, run a fresh
production-to-staging refresh and directly sample the resulting data for
any recognizable real values, confirming none are present. Set up an
ongoing check (part of the refresh pipeline or a periodic audit) that
flags any new schema column matching common PII naming patterns that
isn't yet covered by the anonymization step.
