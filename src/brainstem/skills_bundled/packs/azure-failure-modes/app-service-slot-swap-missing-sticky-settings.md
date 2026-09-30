---
name: app-service-slot-swap-missing-sticky-settings
description: An App Service deployment slot swap completes successfully but the newly swapped-in production slot immediately errors or misbehaves.
triggers: ["app service slot swap breaks production", "slot swap works but app errors after swap", "deployment slot settings not sticky", "app service swap connection string wrong environment"]
permissions: ["READ"]
---

## Symptom
A staging-to-production slot swap in Azure App Service reports success in
the portal/CLI with no errors, but immediately after the swap the app
serving production traffic throws connection errors, authentication
failures, or behaves as if it's still pointed at staging resources (wrong
database, wrong feature flags, wrong external API endpoint). Swapping back
"fixes" it instantly, which looks like a caching issue but isn't.

## Likely causes
1. **App settings or connection strings that should differ per slot were
   never marked "Deployment slot setting" (sticky)**, so the swap operation
   -- which swaps the *code* and *non-sticky* config between slots -- moved
   staging's settings into production instead of leaving production's
   settings in place, because non-sticky settings travel with the swap by
   design.
2. **A setting was marked sticky on one slot but not its counterpart** --
   stickiness is a per-slot, per-setting flag, not a pairing; if only the
   production slot has a setting flagged sticky and staging doesn't (or
   vice versa), the swap's behavior for that key becomes inconsistent
   depending on which slot originated the value.
3. **The app reads configuration into memory only at cold start** and the
   swap didn't trigger a full worker restart in the way assumed, so some
   instances are still serving with the pre-swap in-memory config while
   others have picked up the new (wrong) values, producing intermittent
   rather than uniform failures.
4. **Connection strings for slot-specific resources (e.g., separate
   staging vs. production databases) were set as plain App Settings
   instead of using the Connection Strings section**, and someone assumed
   the Connection Strings blade's different UI implied automatic
   slot-awareness when stickiness still had to be set explicitly there
   too.
5. **A Key Vault reference (`@Microsoft.KeyVault(...)`) in an app setting
   points to a secret that differs by intended environment**, and because
   the reference itself wasn't marked sticky, the swap carried staging's
   Key Vault reference into production, resolving to the wrong secret
   silently (no error at swap time, only at first use).

## Diagnose
- In the Azure portal, go to each slot's Configuration blade and check the
  "Deployment slot setting" checkbox state for every App Setting and
  Connection String -- compare production and staging side by side before
  attempting another swap.
- Use `az webapp config appsettings list --slot <slot>` for both slots and
  diff the output, paying attention to which keys show `"slotSetting":
  true` vs `false`.
- Check Application Insights or App Service logs immediately post-swap for
  the specific error (DB connection refused, 401 from an external API) and
  trace which value (host, key, endpoint) the app actually used -- compare
  it against what staging's pre-swap value was, not production's intended
  value.
- Review the Activity Log for the swap operation itself to confirm exactly
  which settings Azure reports as swapped vs. retained (the swap operation
  detail includes a settings diff).

## Fix
Audit every app setting and connection string that is legitimately
environment-specific (database connection strings, external API base
URLs, feature-flag endpoints, Key Vault references pointing to
environment-scoped secrets) and mark each one as a deployment slot setting
on *both* slots involved in the swap, not just one. Treat "which settings
are sticky" as part of the deployment contract for the app, documented
alongside the swap process, so it isn't rediscovered after each incident.
For settings that must differ, prefer using slot-specific Key Vault
references with distinctly named secrets per environment (e.g.,
`db-connection-prod` vs `db-connection-staging`) so the sticky flag and
the secret naming both make the intent explicit rather than relying on a
single reference name plus a checkbox.

## Pitfalls
Marking *everything* sticky as a defensive overcorrection defeats the
purpose of slots -- if code-level settings that should move with the
deployment (like a feature version tag meant to go live with the new code)
are also marked sticky, the swap silently keeps the old value and the new
code runs against stale configuration, which is the same class of bug
in the opposite direction. Decide sticky-ness per setting based on whether
it identifies "which environment is this" (should be sticky) versus
"what does the currently deployed code expect" (should not be sticky).

## Verify
After correcting stickiness flags, perform a swap and immediately check
`az webapp config appsettings list --slot production` to confirm the
values are the ones that were pinned to production before the swap, not
staging's. Then exercise the specific failing path (a DB query, the
external API call) against production and confirm it succeeds using
production resources. Finally, do a second swap-and-swap-back cycle to
confirm both directions preserve the correct per-slot values.
