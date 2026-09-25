---
name: vault-unsealed-manually-single-point-of-failure
description: A Vault cluster requires manual unsealing after every restart, creating an operational bottleneck and single point of failure when the people holding unseal keys are unavailable.
triggers: ["vault sealed after restart", "vault manual unseal bottleneck", "vault unseal keys unavailable", "vault auto unseal not configured"]
permissions: ["READ"]
---

## Symptom

Every time a Vault node restarts (a deploy, a crash, routine
maintenance), it comes back up in a sealed state requiring manual
intervention -- specific people entering unseal key shares -- before
Vault can serve any requests again, and if those specific people are
unavailable (on vacation, asleep, unreachable), the entire secrets
infrastructure (and everything depending on it) stays down until they
can be reached.

## Likely causes

- **Vault was set up with Shamir's Secret Sharing for unsealing (the
  default) without configuring auto-unseal**, which is a reasonable
  choice for initial setup/high-security environments but requires
  manual key-holder intervention on every restart unless explicitly
  automated.
- **Auto-unseal (via a cloud KMS, HSM, or Vault-to-Vault auto-unseal) was
  never configured**, either because it wasn't set up initially and never
  revisited, or because of an assumption that manual unsealing was
  acceptable that didn't account for how often restarts actually occur in
  practice (deploys, node replacement, crashes).
- **Unseal key shares are held by too few people, or by people who aren't
  actually on-call/available when Vault might need unsealing** (e.g. all
  key holders in the same timezone/organization for a global service, or
  key holders who've since left the team without key rotation).
- **The operational cost of manual unsealing was accepted early on when
  restarts were rare**, but as the deployment scaled (more nodes, more
  frequent deploys/restarts) the manual process became a proportionally
  much bigger operational burden than originally anticipated.

## Diagnose

1. Review how frequently Vault nodes actually restart in the current
   environment (deploy frequency, crash/incident history, infrastructure
   churn) to quantify how often manual unsealing is actually required.
2. Check the current unseal key holder list against the team's actual
   on-call/availability coverage -- confirm key holders can realistically
   be reached within an acceptable time window at any hour, if that's
   required.
3. Check whether the underlying infrastructure (cloud provider, on-prem
   HSM) has a supported auto-unseal mechanism available that just hasn't
   been configured.
4. Review any past incidents where Vault was sealed and unavailable
   longer than acceptable due to unseal key holder unavailability, to
   quantify the real cost of the current manual process.

## Fix

Configure auto-unseal using a cloud KMS (AWS KMS, GCP Cloud KMS, Azure
Key Vault) or an HSM, which removes the need for manual key-share entry
on restart while still requiring the KMS/HSM itself to be available and
appropriately access-controlled -- this shifts the single-point-of-
failure risk to well-tested, highly-available cloud infrastructure rather
than specific individual humans. If manual (Shamir) unsealing is kept
intentionally for security/compliance reasons, ensure key shares are
distributed across enough people with genuinely diverse availability
(different timezones/schedules) to realistically guarantee timely
unsealing, and establish a clear, tested process (not just a
theoretical one) for reaching key holders during an actual incident.

## Pitfalls

Don't treat auto-unseal as removing all operational risk -- it moves the
single point of failure to the KMS/HSM dependency, so that dependency's
own availability and access control become critical; verify its
reliability and access model as carefully as the original manual process.
Also, if keeping manual unsealing intentionally, don't let the actual
key-holder list silently go stale as people change teams/leave the
organization -- audit and rotate key holders periodically.

## Verify

Test the actual unseal process (auto-unseal or manual) by restarting a
Vault node in a non-production environment and confirming it comes back
online within an acceptable time window without requiring an unavailable
dependency. For manual unsealing kept intentionally, run a genuine
tabletop exercise reaching the actual key holders to confirm the process
works in practice, not just in documentation.
