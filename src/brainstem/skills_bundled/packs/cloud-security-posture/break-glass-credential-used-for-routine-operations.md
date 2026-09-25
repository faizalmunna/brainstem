---
name: break-glass-credential-used-for-routine-operations
description: A break-glass emergency-access credential is being used for everyday routine operations instead of being reserved and monitored strictly for genuine emergencies.
triggers: ["we're using the emergency account for regular deploys", "break glass credential shared in normal workflow", "the emergency access account logs in every day", "break glass account isn't actually monitored for exceptional use"]
permissions: ["READ"]
---

## Symptom

Reviewing usage of a designated break-glass/emergency-access account
(the credential meant to bypass normal SSO/MFA flows only when the
primary identity system itself is unavailable) shows frequent, routine
logins -- daily deploys, regular admin tasks -- rather than the rare,
exceptional use it was designed for. The credential has quietly become a
convenience shortcut, which defeats its purpose: it's no longer a
monitored, alarm-triggering exception, it's business as usual.

## Likely causes

- **The break-glass account often has broader, less-restricted
  permissions or bypasses normal MFA/conditional-access controls by
  design**, which makes it an attractive shortcut for engineers who find
  normal privileged access workflows too slow or cumbersome for routine
  tasks.
- **No monitoring/alerting was actually attached to the break-glass
  credential's usage** at the time it was set up, so there's no signal
  telling anyone it's being used outside its intended scope until an
  audit specifically looks at its login history.
- **The primary access-request/approval workflow for routine privileged
  tasks has too much friction** (slow ticket approval, over-restrictive
  standard roles), so people route around it via the one account that
  doesn't require going through that process, without necessarily
  understanding it was meant to be reserved for outages.
- **Knowledge of the credential's intended purpose wasn't preserved
  through team turnover** -- the people who set up the break-glass
  process and its intended narrow scope have moved on, and current users
  just see "the account that always works" without the original
  context.

## Diagnose

1. Pull the full login/usage history for every designated break-glass
   account and check the frequency -- genuine emergency use should be
   rare (ideally zero to a handful of times per year); anything
   resembling daily or weekly regular use confirms the pattern.
2. For each usage event, check whether it correlates with an actual
   documented incident/outage of the primary identity system, versus
   correlating with routine deploy schedules or convenience timing
   (e.g., always used right before a release).
3. Check what alerting currently exists on break-glass account usage --
   confirm whether any notification fires on login at all, since the
   absence of any historical alert despite frequent use indicates
   monitoring was never wired up.
4. Check the account's actual permission scope and MFA/conditional-access
   exemption status to confirm it does in fact bypass controls that
   would otherwise apply, which is what makes routine use of it a
   meaningful security regression rather than a harmless habit.

## Fix

Restrict the break-glass credential to only be usable through a
process that makes routine use impractical and emergency use fast:
sealed/vaulted storage requiring a documented justification and
multi-person approval or notification to retrieve, paired with
mandatory, immediate, high-priority alerting to the security team on
every single use with no exceptions. Separately, fix the underlying
friction that pushed people toward the shortcut -- streamline the
normal privileged-access request workflow for legitimate routine tasks
so there's no incentive to reach for the emergency account instead.
Rotate the break-glass credential immediately after this discovery,
since its routine use means its current form should be treated as
having had broader exposure than intended.

## Pitfalls

Don't solve this purely by writing a policy document saying "don't use
break-glass for routine work" without also removing the operational
friction that made people reach for it -- a policy with no enforcement
mechanism against a credential that's easier to use than the sanctioned
path will keep losing to convenience.

## Verify

Confirm every use of the break-glass credential going forward triggers
an immediate alert to the security team, by performing a test retrieval
in a controlled way and confirming the alert fires. Track usage
frequency over the following quarter and confirm it drops to the rare,
incident-correlated pattern expected of genuine emergency access, not
the routine pattern originally found.
