---
name: eloquent-global-scope-unexpectedly-filtering-records
description: A query against an Eloquent model returns fewer rows than the database actually contains because a global scope is silently applying a filter.
triggers: ["eloquent query missing rows that exist", "global scope filtering unexpectedly", "count doesn't match database laravel", "withoutGlobalScopes needed"]
permissions: ["READ"]
---

## Symptom
`Model::count()`, `Model::all()`, or a specific `where()` query returns
fewer rows than a direct `SELECT count(*) FROM table` against the same
database shows -- and the discrepancy isn't explained by any `where()`
clause visible at the call site, making it look like data loss or a
replication lag issue when the rows are actually present and simply
being filtered out before the query result reaches the caller.

## Likely causes
1. **A global scope defined via `static::addGlobalScope(...)` in the
   model's `booted()`/`boot()` method (or an `implements ScopeInterface`
   class) applies a `where()` condition to every query on that model**,
   and the call site has no way to see this by reading the query call
   itself -- the filtering logic lives in the model definition, not at
   the point of use, which is exactly why it's easy to forget about
   months after it was added.
2. **`SoftDeletes` is in use, and the "missing" rows are actually
   soft-deleted** -- the `deleted_at IS NULL` global scope `SoftDeletes`
   adds is the single most common source of this symptom, especially
   for anyone newer to a codebase who doesn't yet know soft deletes are
   enabled on this particular model.
3. **A multi-tenancy global scope automatically filters by the current
   tenant/team/organization context**, and the query is being run from a
   context where that tenant scope resolves to the wrong tenant (or
   `null`) -- e.g. a queued job or a console command running outside the
   normal request lifecycle where the tenant-resolution logic (often
   based on the authenticated user or a request header) has nothing to
   resolve, so the scope either filters everything out or throws in a way
   that gets swallowed upstream.
4. **A scope was added to fix one specific business rule (e.g. "only show
   published posts") in a way that was intended for the public-facing
   controller only, but was implemented as a global scope**, so it now
   also silently applies inside admin tools, reports, and console commands
   that need to see *all* records regardless of publication status.

## Diagnose
- Run `Model::withoutGlobalScopes()->count()` versus plain
  `Model::count()` in tinker -- a difference between the two numbers
  confirms a global scope is responsible and quantifies exactly how many
  rows are being filtered.
- Check the model class (and any trait it uses) for `addGlobalScope`
  calls in `booted()`, and check for `use SoftDeletes;` -- both are easy
  to miss in a quick read of the model if the file is long or the trait
  is applied several classes up an inheritance chain.
- If a global scope is confirmed, dump the actual SQL it appends
  (`Model::query()->toSql()` and `->getBindings()`) to see the exact
  condition and, for context-dependent scopes (tenant/team), what value
  it's actually filtering on in the failing environment (console command,
  queued job, etc.).
- For console commands/queued jobs specifically, check how the
  tenant/context-resolving code determines "current tenant" (usually via
  `auth()->user()` or middleware-set state) and confirm that context
  actually exists when running outside an HTTP request -- it frequently
  doesn't, since there's no authenticated request in that path.

## Fix
- For a legitimate, intentional global scope (soft deletes, tenant
  isolation), use the provided escape hatches explicitly wherever the
  scope's default doesn't apply: `withTrashed()`/`onlyTrashed()` for soft
  deletes, or the tenant-scope package's documented bypass
  (`withoutGlobalScope(TenantScope::class)`) for admin/cross-tenant
  contexts -- rather than removing the scope from the model, which would
  reopen the isolation gap for everywhere else that correctly relies on
  it.
- For a global scope that was really meant to be a *local* scope for one
  specific use case (public "published only" listings), convert it to a
  named local scope (`scopePublished($query)`) applied explicitly at the
  call sites that need it, and remove the global registration -- this
  makes the filtering visible at the point of use instead of hidden in
  the model definition, and stops it from silently affecting admin/report
  code that shouldn't be filtered.
- For context-dependent scopes running in console commands/queued jobs,
  either explicitly set the required context before the query runs (pass
  the tenant ID into the job/command and set it explicitly rather than
  relying on auth state), or bypass the scope deliberately with a clear
  comment explaining why that code path is intentionally cross-tenant/
  cross-context.
- Document every global scope's existence somewhere discoverable (a
  comment on the model class listing active global scopes and what each
  one filters), since their entire risk profile is that they're invisible
  at the call site.

## Pitfalls
- Reflexively calling `withoutGlobalScopes()` everywhere a count/query
  looks "wrong" without first understanding *which* scope and *why* it
  exists can silently defeat a security-relevant scope (tenant isolation,
  soft-delete-based "not really deleted" semantics) -- confirm which
  scope is responsible and whether bypassing it here is actually safe
  before reaching for the blanket bypass.
- Removing a global scope from the model to fix one broken call site
  changes behavior for every other call site in the app that was
  correctly relying on the automatic filtering -- prefer scoping the fix
  to the specific call site (`withoutGlobalScope`) or converting to a
  local scope over removing the global scope outright.
- Assuming `withTrashed()` is a permanent, safe default for admin tooling
  without considering that some business logic (e.g. sending
  notifications, applying business rules) may not be meant to apply to
  soft-deleted records even in an admin context -- use the trashed-record
  visibility narrowly, for viewing/reporting, not for re-triggering
  logic meant only for active records.

## Verify
Run `Model::withoutGlobalScopes()->count()` and plain `Model::count()`
side by side and confirm the difference matches the expected, understood
filtering (e.g. exactly the number of soft-deleted rows, verified
separately via `Model::onlyTrashed()->count()`) rather than an unexplained
remainder. For a context-dependent scope fix in a console command or
job, run that command/job in the same environment it runs in production
(not just via a web request in local dev) and confirm it now returns the
expected full/correct result set.
