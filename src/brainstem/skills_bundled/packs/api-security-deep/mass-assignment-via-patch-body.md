---
name: mass-assignment-via-patch-body
description: A PATCH or PUT endpoint blindly assigns every field in the request body to the database model, letting a client set fields like is_admin that should never be client-controllable.
triggers: ["user set themselves as admin through profile update", "mass assignment vulnerability in API", "client controlled field that should be server only", "PATCH request modified fields it shouldn't have access to"]
permissions: ["READ"]
---

## Symptom
A user updates their own profile via `PATCH /users/me` with a body they control, and afterward fields that were never shown in the UI -- `is_admin`, `role`, `account_balance`, `verified`, `subscription_tier` -- have changed to attacker-chosen values. Nothing in the code explicitly sets those fields from user input; the vulnerability is in how the update is implemented, not in an obvious explicit assignment.

## Likely causes
1. **The handler does `model.update(**request.json)` or equivalent generic deserialization** (Django `ModelForm` without explicit fields, SQLAlchemy `for k,v in data.items(): setattr(obj,k,v)`, Rails `update_attributes(params)` without strong params, a naive `Object.assign(user, req.body)`), so any key present in the request body maps directly onto any model attribute of the same name.
2. **The serializer/schema used for input validation is the same one used for output**, so it "knows about" privileged fields (because they need to be serialized back to admins) and that knowledge leaks into what's accepted on write too.
3. **An allowlist exists but is incomplete or was written before a sensitive field was added** -- a new column like `credit_limit` or `role` got added to the model and the ORM's default behavior included it in mass updates before anyone thought to exclude it explicitly (denylist-based protection instead of allowlist-based).
4. **Nested/related objects bypass the top-level field filter** -- the endpoint correctly restricts top-level fields but accepts a nested object (e.g. `{"profile": {...}, "account": {"balance": 999999}}`) that gets passed through to a related model's mass-assignment separately.

## Diagnose
- Grep the codebase for generic update patterns: `**request.json`, `**data`, `.update(request.data)`, `setattr(obj, key, value)` in a loop, `Object.assign(model,`, or ORM calls that accept a raw dict/params object without an explicit field list.
- For the specific endpoint in question, send a PATCH/PUT request in a test environment with an extra field not shown in any UI or API docs (e.g. `{"name": "test", "is_admin": true}`) and check whether the response or a follow-up GET reflects the unauthorized field change.
- Check whether input validation schema (Pydantic/serializer/DTO) explicitly enumerates writable fields, or whether it's generated from the model's full column list (a common default in scaffolding tools that silently includes every column).
- Audit which fields on the model are genuinely user-writable vs. server-only (role, balance, verification status, timestamps, foreign keys to other users) and confirm each server-only field has an explicit reason it's excluded from the write path, not just "nobody noticed yet."

## Fix
Require an explicit allowlist of writable fields per endpoint/role, never a denylist or blind pass-through:
- Define a dedicated input schema per write operation (e.g. `UserProfileUpdateInput` with only `name`, `bio`, `avatar_url`) that is structurally incapable of carrying `is_admin` or `balance` -- validation libraries (Pydantic, Zod, Rails strong parameters, Django serializers with explicit `fields`) should reject unknown fields (`extra="forbid"`/`strict`) rather than silently ignoring or accepting them.
- Keep read/output serializers separate from write/input serializers even when they look similar, since a shared schema is how privileged fields sneak into the writable set.
- For fields that are writable only by certain roles (e.g. an admin can set another user's `role`, but the user cannot set their own), enforce that at the field level with an explicit role check, not by relying on the endpoint being "admin-only" as a whole -- endpoints get reused across roles more often than expected.
- Apply the same allowlist discipline to nested/related objects in the payload; validate and filter each nested structure through its own explicit schema rather than passing it through to a related model's update.

## Pitfalls
Don't fix this by adding the newly-discovered dangerous field to a denylist ("exclude `is_admin` from mass assignment") -- the next sensitive field added to the model (a new `is_verified` or `stripe_customer_id` column) will be mass-assignable by default again until someone remembers to denylist it too. Allowlisting is the only version of this fix that doesn't regress silently on schema changes.

## Verify
Add a test that PATCHes the endpoint with a payload containing every column on the underlying model, including newly-added and privileged ones, and assert that only the explicitly-allowed fields changed and the response is either a validation error or a silent ignore for the rest -- run this test as part of CI so a new model column can't reintroduce the hole unnoticed.
