---
name: entra-id-conditional-access-inconsistent-token-failure
description: Azure AD (Entra ID) token acquisition fails intermittently for some users or client types while others authenticate successfully with identical credentials.
triggers: ["azure ad token acquisition fails intermittently", "conditional access blocking some clients not others", "entra id interrupt error only on some devices", "AADSTS50076 AADSTS53003 intermittent"]
permissions: ["READ"]
---

## Symptom
Users report intermittent authentication failures acquiring an Azure AD
(Entra ID) token -- sometimes an `AADSTS53003` (blocked by Conditional
Access) or `AADSTS50076`/`AADSTS50079` (MFA required) error, sometimes
silent failure of a background/daemon token refresh -- but the same
identity succeeds from a different device, browser, or client library
minutes later. It isn't a wholesale outage: it correlates with *which*
client is asking, not a single root cause visible from the app's own logs.

## Likely causes
1. **Conditional Access policies target client app or platform
   conditions that a public client (mobile app, CLI, service principal)
   can't satisfy the same way a browser-based interactive sign-in can**
   -- e.g., a policy requiring a compliant/hybrid-joined device or MFA
   applies cleanly to interactive browser flows but breaks a background
   daemon using client-credentials flow, which has no interactive session
   to satisfy an MFA challenge at all.
2. **Token caching and silent refresh (MSAL's `acquireTokenSilent`)
   succeeds using a previously-issued refresh token that predates a newly
   applied or newly tightened Conditional Access policy**, so some clients
   keep working off a cached grant while any client forced into a fresh
   interactive flow immediately hits the new policy -- this looks
   "intermittent" but is actually a propagation/cache-age difference.
3. **Named locations (trusted IP ranges) used in the Conditional Access
   policy are stale or incomplete**, so users on a VPN egressing through
   an IP not in the named location list get challenged or blocked while
   users on office Wi-Fi (whose IP is listed) sail through, producing
   failures that look random unless correlated with network path.
4. **Policy targeting a group has replication/propagation lag** after a
   user is added to or removed from a security group used in Conditional
   Access assignment -- Entra ID group membership changes can take time to
   be evaluated consistently across all token issuance endpoints, so the
   same user can get different policy outcomes for a short window.
5. **Session controls (sign-in frequency, persistent browser session) are
   configured differently across policies that both match the same user**,
   and Conditional Access policy evaluation combines multiple matching
   policies -- the *most restrictive* combined result wins, which can
   produce a stricter outcome than any single policy's author expected,
   especially after a second policy was added later without re-reviewing
   interactions with the first.

## Diagnose
- Pull the Entra ID **Sign-in logs** (Azure portal > Entra ID > Sign-in
  logs, or `az monitor` / Log Analytics if exported) for the failing
  correlation ID and open the "Conditional Access" tab on that sign-in
  event -- it lists every policy evaluated and whether each individually
  applied, was not applicable, or wasn't satisfied, which is far more
  precise than the raw AADSTS error code alone.
- Compare a failing sign-in's **Client app** and **Device** fields against
  a succeeding one for the same user -- if the client app differs (e.g.,
  "Mobile Apps and Desktop clients" vs. "Browser"), the policy's client-app
  condition scoping is the likely culprit.
- Check the failing sign-in's **Location** (resolved from source IP) against
  the named locations configured in the applicable Conditional Access
  policy to rule out an incomplete trusted-IP range.
- For service principals / daemons using client-credentials flow, confirm
  whether any Conditional Access policy targeting "all cloud apps" or "all
  users" inadvertently includes workload identities -- policies meant for
  interactive users can unintentionally scope to service principals unless
  explicitly excluded (or unless using the newer Conditional Access for
  workload identities feature deliberately).
- Use the **What If** tool under Entra ID > Conditional Access to simulate
  the exact user/app/platform/location combination that failed and see
  which policies the simulator says should apply -- if it disagrees with
  the sign-in log's actual result, group membership propagation lag is a
  likely factor.

## Fix
Scope Conditional Access policies explicitly by client app type and
platform rather than relying on "all apps" defaults, and write a separate,
deliberately-designed policy for non-interactive identities (service
principals, managed identities) using the workload identity Conditional
Access surface instead of assuming user-facing MFA/device-compliance
policies gracefully no-op for them. Keep named locations current
(especially VPN/NAT egress ranges) and review them whenever network
infrastructure changes. When multiple policies can match the same
sign-in, document the intended combined effect and periodically audit
overlapping policies for unintended compounding restrictions, rather than
adding new policies in isolation.

## Pitfalls
Excluding a service principal or break-glass account from Conditional
Access entirely to "unblock" a token failure, without narrowing the
exclusion's scope or adding compensating controls, creates a standing
security gap that persists long after the original incident is forgotten.
Similarly, widening a named-location range to include an entire cloud
provider's IP space (to catch a VPN egress IP) can defeat the purpose of
location-based policy for unrelated traffic from the same range.

## Verify
Re-run the What-If simulator for the exact combination that previously
failed and confirm the expected policy outcome. Have an affected user or
service perform a fresh (non-cached) sign-in or client-credentials request
and confirm success in the Sign-in logs, checking the Conditional Access
tab shows all intended policies as "Satisfied" rather than "Not
applicable" due to a scoping gap. Monitor sign-in failure rates segmented
by client app type for the following days to confirm the fix didn't just
move the failure to a different client population.
