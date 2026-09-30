---
name: mass-assignment-missing-fillable-guarded
description: A user submits extra form fields like is_admin or role_id and the Eloquent model saves them because fillable or guarded was never defined.
triggers: ["mass assignment vulnerability laravel", "user can set is_admin field", "eloquent fillable missing", "unexpected fields saved to database"]
permissions: ["READ"]
---

## Symptom
A user (or an attacker) submits a request with extra fields that weren't
part of the intended form -- `is_admin=1`, `role_id=1`, `verified=true`,
`user_id=<someone else's id>` -- and those fields end up written to the
database via `Model::create($request->all())` or `$model->update($request
->all())`, even though the UI never exposed a control for them. This is
often discovered via a security audit or bug bounty report rather than
normal QA, because the app "works correctly" for every legitimate user
flow.

## Likely causes
1. **The model has neither `$fillable` nor `$guarded` defined**, or has
   `protected $guarded = [];`, which tells Eloquent every attribute is
   mass-assignable -- a common shortcut taken during early development
   ("I'll lock it down later") that survives into production because it
   never causes a visible bug for legitimate users.
2. **`$request->all()` (or `$request->input()` with no key list) is
   passed directly into `create()`/`update()`/`fill()`** instead of a
   validated, explicitly-listed subset of fields -- even a model with a
   correct `$fillable` list is still at risk if the *validation* layer
   doesn't reject unexpected keys, because `$fillable` only controls what
   Eloquent *writes*, not what the request is allowed to contain, so
   sibling issues like unexpected keys silently passing `$request
   ->validated()` when the validation rules are incomplete (missing
   `sometimes`/rejecting unknown keys) compound the risk.
3. **A field was intentionally excluded from `$fillable` for security
   (e.g. `role_id`), but a later refactor added it back via
   `$model->forceFill($request->all())`** -- `forceFill()` deliberately
   bypasses mass-assignment protection entirely, and it's easy to reach
   for during a "why won't this field save" debugging session without
   realizing it removes the protection for every field, not just the one
   causing trouble.
4. **The `$fillable` list is correct on the primary model but a related
   model saved in the same request (e.g. via a nested `create()` on a
   relationship, or a form request that touches multiple models) has no
   protection at all** -- the audit focused on the "main" model and
   missed a secondary one touched by the same endpoint.

## Diagnose
- For the affected model, check for `$fillable`/`$guarded` -- an empty
  `$guarded = []` or the total absence of either property means every
  column is mass-assignable right now.
- Grep the controller/service layer for `::create($request->all())`,
  `->update($request->all())`, `->fill($request->all())`, and any
  `forceFill(` call -- each is a candidate for this vulnerability
  regardless of what `$fillable` says, since `forceFill` ignores it
  entirely.
- Reproduce directly: send a request through the actual endpoint (Postman
  /curl, not just the UI) with an extra field like `is_admin=1` added to
  a legitimate-looking payload, and check the database row afterward to
  see if it was written.
- Check `Model::preventSilentlyDiscardingAttributes()` (Laravel 10.16+) --
  if it's not enabled in a service provider's `boot()` in non-production
  environments, mass-assignment mismatches fail silently during
  development instead of throwing, which is part of why they reach
  production unnoticed.

## Fix
- Define an explicit `$fillable` allowlist naming exactly the attributes
  that should ever be settable via mass assignment for that model,
  rather than `$guarded = []` or an implicit "everything is fillable"
  state -- an allowlist fails safe when a new sensitive column is added
  later, since it has to be explicitly opted in rather than accidentally
  exposed.
- Validate requests with a Form Request class that lists exactly the
  expected fields and pass `$request->validated()` (not `$request
  ->all()`) into `create()`/`update()` -- this closes the gap even for
  fields that might slip past a slightly-too-permissive `$fillable` list,
  since validation controls what's *accepted*, and `$fillable` controls
  what's *written*; you need both layers.
- Reserve `forceFill()`/`$guarded = []` for genuinely trusted, internal
  code paths (an internal admin tool operating on already-validated data,
  a data migration script) and never for anything touching raw user
  input -- if a legitimate field "won't save" during debugging, fix the
  `$fillable` list to include it explicitly instead of reaching for
  `forceFill()`.
- Audit every model touched by a given endpoint, not just the primary
  one -- for nested relationship saves, confirm the related model also
  defines its own `$fillable`/`$guarded`, since Eloquent's mass-assignment
  protection is per-model, not inherited from the parent relationship.

## Pitfalls
- Setting `$guarded = ['id']` and assuming that's sufficient protection
  guards only the primary key -- it leaves every other column, including
  sensitive ones added later, mass-assignable by default. Prefer
  `$fillable` (allowlist) over `$guarded` (denylist) for any model with
  security-sensitive columns, since a denylist has to be remembered and
  updated every time a sensitive column is added.
- Fixing the model's `$fillable` but leaving `$request->all()` in the
  controller still leaves a validation-layer gap for anything the
  `$fillable` list currently includes but shouldn't be settable in *this
  specific* request context (e.g. `status` is fillable for an admin
  endpoint but the same model is also updated from a public-facing
  endpoint that reuses the same `update()` call).
- Over-restricting `$fillable` as a blanket security response can silently
  break legitimate features that relied on mass-assigning a field --
  after tightening it, run through the actual feature flows that write to
  the model (not just the exploit reproduction) to confirm nothing
  legitimate broke.

## Verify
Repeat the exact reproduction request from the diagnose step (extra field
like `is_admin=1` added to a legitimate payload) against the fixed
endpoint and confirm the database row does *not* contain the injected
value, while a request with only the legitimate fields still saves
correctly. Additionally confirm `Model::preventSilentlyDiscardingAttributes()`
is active in local/testing environments so a future reintroduction of
this pattern throws during development instead of shipping silently.
