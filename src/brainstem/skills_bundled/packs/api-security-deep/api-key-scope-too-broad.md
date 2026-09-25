---
name: api-key-scope-too-broad
description: An API key issued for one narrow purpose has full account or admin-level permissions, so a leak of that single key exposes far more than intended.
triggers: ["API key has more access than it needs", "leaked read only key was actually full access", "no way to scope API key permissions", "third party integration key can do everything"]
permissions: ["READ"]
---

## Symptom
A key issued for a specific integration -- a read-only analytics export, a webhook-receiver credential, a single third-party plugin -- turns out, when leaked or audited, to have the same permissions as a full admin/account owner key: it can read all data, write/delete records, manage billing, or create other API keys, even though the integration it was actually issued for only ever calls two or three read endpoints.

## Likely causes
1. **The API only supports one key tier** -- keys are validated as "valid for this account" with no concept of scopes/permissions attached at issuance, so every key implicitly has whatever the account itself can do.
2. **A scoping system exists but defaults to maximum permissions unless narrowed**, and narrowing is a manual step in the key-creation UI/API that's easy to skip -- so keys are routinely issued at full scope because that's the path of least resistance, not because the issuer intended it.
3. **Scopes exist and are set narrowly at issuance, but aren't actually enforced server-side** -- the authorization check for each endpoint verifies "is this a valid key for this account" but never checks "does this key's scope include this specific action," so the scope field is descriptive metadata rather than an enforced boundary.
4. **A key was originally issued narrowly but scope crept over time** as the integration was extended to call more endpoints, and each extension quietly widened the key's permissions (or the team just reissued a full-access key rather than adding one specific new scope) rather than reviewing what the minimum necessary set actually was.

## Diagnose
- Pick a sample of currently-issued API keys and, for each, compare what the integration actually calls (from access logs) against what the key is authorized to do -- a large gap between "used" and "permitted" endpoints indicates over-scoping.
- Check the authorization middleware for each endpoint: does it check the calling key's specific scope/permission list, or only that the key is valid and belongs to an account with access? Grep for where `request.api_key.scopes` (or equivalent) is actually consulted versus where only key validity is checked.
- Check the key-issuance flow/UI: is there a scope-selection step, and what's the default state (all scopes pre-checked vs. none)? A default-to-everything UI reliably produces over-scoped keys regardless of good intentions.
- Review recent incidents or leaked-key reports (if any) for what the leaked key was actually able to do versus what the integration needed -- this quantifies the real blast-radius reduction scoping would have provided.

## Fix
Build and enforce least-privilege scopes as a first-class part of the key lifecycle:
- Define a granular scope model (e.g. `orders:read`, `orders:write`, `webhooks:receive`) and require every endpoint's authorization check to verify the calling key's scope includes the specific action, not just that the key is valid for the account -- scope must be enforced at the authorization layer, not just recorded as metadata.
- Default key creation to zero or minimal scope, requiring explicit selection of each needed permission, and surface in the creation UI/API exactly what each scope grants in plain language so issuers can make an informed minimal choice.
- Periodically audit issued keys against actual usage (from access logs) and flag keys whose granted scope significantly exceeds their observed usage for review/tightening.
- When an integration needs a new capability, add the specific new scope to that key rather than reissuing it with broader or full access, and treat "just give it admin, it's easier" as a rejected shortcut in code review for key-issuance code.

## Pitfalls
Don't build a scope system that's advisory only (shown in a dashboard, checked by nothing) -- an unenforced scope model gives a false sense of least-privilege while providing zero actual blast-radius reduction when a key leaks, which is worse than no scope system because it's actively misleading during incident response.

## Verify
Issue a test key with a narrow scope (e.g. read-only on one resource), then attempt a write operation and an operation on a different resource type using that key, and confirm both are rejected with 403 even though the key is otherwise valid -- then confirm the same key's permitted read operation succeeds.
